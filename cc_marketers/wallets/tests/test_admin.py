# wallets/tests/test_admin.py
from django.test import  Client
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import format_html
from decimal import Decimal
from unittest.mock import Mock, patch

from ..admin import WalletAdmin, TransactionAdmin, EscrowTransactionAdmin, WithdrawalRequestAdmin
from ..models import Wallet, Transaction, EscrowTransaction, WithdrawalRequest
from .test_base import WalletTestCase

User = get_user_model()


class WalletAdminTest(WalletTestCase):
    """Test WalletAdmin functionality"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.wallet_admin = WalletAdmin(Wallet, self.site)
        
        # Fund wallet for testing
        self.wallet.balance = Decimal('500.00')
        self.wallet.save()
        
        # Create some transactions for total_earned calculation
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='task_earning',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00'),
            status='success'
        )
        
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='referral_bonus',
            amount=Decimal('50.00'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('150.00'),
            status='success'
        )
    
    def test_list_display(self):
        """Test wallet admin list display"""
        expected_fields = ['user', 'balance', 'available_balance_display', 'total_earned', 'created_at']
        self.assertEqual(list(self.wallet_admin.list_display), expected_fields)
    
    def test_available_balance_display_method(self):
        """Test available_balance_display method formatting"""
        # Create pending withdrawal to test available balance calculation
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
        
        self.wallet.refresh_from_db()
        result = self.wallet_admin.available_balance_display(self.wallet)
        
        # Should display available balance (500 - 100 = 400) in green
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">${}</span>',
            'green',
            '400.00'
        )
        self.assertEqual(result, expected)
    
    def test_available_balance_display_negative(self):
        """Test available_balance_display with negative balance (edge case)"""
        # Set wallet to negative balance (edge case)
        self.wallet.balance = Decimal('-50.00')
        self.wallet.save()
        
        result = self.wallet_admin.available_balance_display(self.wallet)
        
        # Should display in red for negative balance
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">${}</span>',
            'red',
            '-50.00'
        )
        self.assertEqual(result, expected)
    
    def test_total_earned_calculation(self):
        """Test total_earned method calculation"""
        result = self.wallet_admin.total_earned(self.wallet)
        
        # Should sum task_earning and referral_bonus transactions
        self.assertEqual(result, '$150.00')  # 100.00 + 50.00
    
    def test_total_earned_no_earnings(self):
        """Test total_earned with no earning transactions"""
        # Create wallet for user with no earnings
        new_user = User.objects.create_user(
            username='noearnings',
            email='noearnings@example.com',
            password='pass123'
        )
        new_wallet = Wallet.objects.create(user=new_user)
        
        result = self.wallet_admin.total_earned(new_wallet)
        self.assertEqual(result, '$0.00')
    
    def test_readonly_fields(self):
        """Test that created_at and updated_at are readonly"""
        self.assertIn('created_at', self.wallet_admin.readonly_fields)
        self.assertIn('updated_at', self.wallet_admin.readonly_fields)
    
    def test_list_filter_and_search(self):
        """Test list filter and search fields configuration"""
        self.assertIn('created_at', self.wallet_admin.list_filter)
        expected_search = ['user__username', 'user__email']
        self.assertEqual(list(self.wallet_admin.search_fields), expected_search)


class TransactionAdminTest(WalletTestCase):
    """Test TransactionAdmin functionality"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.transaction_admin = TransactionAdmin(Transaction, self.site)
        
        self.task = self.create_task(self.user, "Admin Test Task")
        
        self.transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='task_earning',
            amount=Decimal('125.50'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('125.50'),
            reference='VERY_LONG_REFERENCE_STRING_FOR_TESTING_TRUNCATION',
            description='Test transaction for admin',
            task=self.task
        )
    
    def test_list_display(self):
        """Test transaction admin list display"""
        expected_fields = [
            'reference_short', 'user', 'transaction_type', 'category', 
            'amount_display', 'status', 'task_link', 'created_at'
        ]
        self.assertEqual(list(self.transaction_admin.list_display), expected_fields)
    
    def test_reference_short_method(self):
        """Test reference_short method truncation"""
        result = self.transaction_admin.reference_short(self.transaction)
        
        # Should truncate long reference
        expected = 'VERY_LONG_REFE...'  # 15 chars + '...'
        self.assertEqual(result, expected)
        
        # Test short reference (no truncation)
        self.transaction.reference = 'SHORT_REF'
        result = self.transaction_admin.reference_short(self.transaction)
        self.assertEqual(result, 'SHORT_REF')
    
    def test_amount_display_credit(self):
        """Test amount_display for credit transactions"""
        result = self.transaction_admin.amount_display(self.transaction)
        
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">{} ${}</span>',
            'green',
            '+',
            '125.50'
        )
        self.assertEqual(result, expected)
    
    def test_amount_display_debit(self):
        """Test amount_display for debit transactions"""
        debit_transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='debit',
            category='withdrawal',
            amount=Decimal('75.25'),
            balance_before=Decimal('125.50'),
            balance_after=Decimal('50.25')
        )
        
        result = self.transaction_admin.amount_display(debit_transaction)
        
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">{} ${}</span>',
            'red',
            '-',
            '75.25'
        )
        self.assertEqual(result, expected)
    
    def test_task_link_with_task(self):
        """Test task_link method with associated task"""
        with patch('django.urls.reverse') as mock_reverse:
            mock_reverse.return_value = '/admin/tasks/task/1/change/'
            
            result = self.transaction_admin.task_link(self.transaction)
            
            expected = format_html(
                '<a href="{}" target="_blank">{}</a>', 
                '/admin/tasks/task/1/change/', 
                self.task.title   # ✅ match admin.py
            )

            self.assertEqual(result, expected)
    
    def test_task_link_without_task(self):
        """Test task_link method without associated task"""
        self.transaction.task = None
        result = self.transaction_admin.task_link(self.transaction)
        self.assertEqual(result, '-')
    
    def test_list_filter_configuration(self):
        """Test list filter configuration"""
        expected_filters = ['transaction_type', 'category', 'status', 'created_at']
        self.assertEqual(list(self.transaction_admin.list_filter), expected_filters)
    
    def test_search_fields_configuration(self):
        """Test search fields configuration"""
        expected_search = ['user__username', 'reference', 'description']
        self.assertEqual(list(self.transaction_admin.search_fields), expected_search)
    
    def test_readonly_fields_configuration(self):
        """Test readonly fields configuration"""
        expected_readonly = ['id', 'created_at', 'updated_at']
        self.assertEqual(list(self.transaction_admin.readonly_fields), expected_readonly)


class EscrowTransactionAdminTest(WalletTestCase):
    """Test EscrowTransactionAdmin functionality"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.escrow_admin = EscrowTransactionAdmin(EscrowTransaction, self.site)
        
        self.task = self.create_task(self.user, "Escrow Admin Test Task")
        self.escrow = EscrowTransaction.objects.create(
            task=self.task,
            advertiser=self.user,
            amount=Decimal('200.00'),
            status='locked'
        )
    
    def test_list_display(self):
        """Test escrow admin list display"""
        expected_fields = ['task_link', 'advertiser', 'amount', 'status', 'created_at', 'released_at']
        self.assertEqual(list(self.escrow_admin.list_display), expected_fields)
    
    def test_task_link_method(self):
        """Test task_link method"""
        with patch('django.urls.reverse') as mock_reverse:
            mock_reverse.return_value = '/admin/tasks/task/1/change/'
            
            result = self.escrow_admin.task_link(self.escrow)
            
            expected = format_html(
                '<a href="{}" target="_blank">{}</a>', 
                '/admin/tasks/task/1/change/', 
                self.task.title
            )
            self.assertEqual(result, expected)
    
    def test_task_link_no_task(self):
        """Test task_link method with no task (edge case)"""
        self.escrow.task = None
        result = self.escrow_admin.task_link(self.escrow)
        self.assertEqual(result, '-')
    
    def test_list_filter_and_search(self):
        """Test list filter and search configuration"""
        self.assertIn('status', self.escrow_admin.list_filter)
        self.assertIn('created_at', self.escrow_admin.list_filter)
        
        expected_search = ['task__title', 'advertiser__username']
        self.assertEqual(list(self.escrow_admin.search_fields), expected_search)


class WithdrawalRequestAdminTest(WalletTestCase):
    """Test WithdrawalRequestAdmin functionality"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.withdrawal_admin = WithdrawalRequestAdmin(WithdrawalRequest, self.site)
        
        self.withdrawal = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('150.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
    
    def test_list_display(self):
        """Test withdrawal admin list display"""
        expected_fields = [
            'id_short', 'user', 'amount', 'withdrawal_method', 
            'status_display', 'created_at', 'processed_by'
        ]
        self.assertEqual(list(self.withdrawal_admin.list_display), expected_fields)
    
    def test_id_short_method(self):
        """Test id_short method truncation"""
        result = self.withdrawal_admin.id_short(self.withdrawal)
        
        # Should show first 8 characters + '...'
        withdrawal_id_str = str(self.withdrawal.id)
        expected = withdrawal_id_str[:8] + '...'
        self.assertEqual(result, expected)
    
    def test_status_display_method(self):
        """Test status_display method with different statuses"""
        # Test pending status
        result = self.withdrawal_admin.status_display(self.withdrawal)
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            '#f59e0b',  # Orange for pending
            'Pending'
        )
        self.assertEqual(result, expected)
        
        # Test approved status
        self.withdrawal.status = 'approved'
        result = self.withdrawal_admin.status_display(self.withdrawal)
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            '#10b981',  # Green for approved
            'Approved'
        )
        self.assertEqual(result, expected)
        
        # Test rejected status
        self.withdrawal.status = 'rejected'
        result = self.withdrawal_admin.status_display(self.withdrawal)
        expected = format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            '#ef4444',  # Red for rejected
            'Rejected'
        )
        self.assertEqual(result, expected)
    
    def test_fieldsets_configuration(self):
        """Test fieldsets configuration"""
        fieldsets = self.withdrawal_admin.fieldsets
        
        # Check that fieldsets are properly structured
        self.assertIsInstance(fieldsets, tuple)
        self.assertEqual(len(fieldsets), 5)  # 5 fieldset sections
        
        # Check section names
        section_names = [section[0] for section in fieldsets]
        expected_names = ['Request Details', 'Bank Details', 'Processing', 'Gateway Details', 'System']
        self.assertEqual(section_names, expected_names)
    
    def test_readonly_fields_configuration(self):
        """Test readonly fields configuration"""
        expected_readonly = ['id', 'created_at', 'gateway_response']
        self.assertEqual(list(self.withdrawal_admin.readonly_fields), expected_readonly)
    
    @patch('wallets.services.WalletService.approve_withdrawal')
    def test_approve_selected_action(self, mock_approve):
        """Test approve_selected admin action"""
        # Create another pending withdrawal
        withdrawal2 = WithdrawalRequest.objects.create(
            user=self.other_user,
            amount=Decimal('75.00'),
            withdrawal_method='bank_transfer',
            account_number='0987654321',
            account_name='Other Account',
            bank_name='Other Bank',
            status='pending'
        )
        
        # Mock successful approval
        mock_approve.return_value = None
        
        # Create mock request and queryset
        mock_request = Mock()
        mock_request.user = self.admin_user
        
        queryset = WithdrawalRequest.objects.filter(status='pending')
        
        # Execute action
        self.withdrawal_admin.approve_selected(mock_request, queryset)
        
        # Should call approve for each pending withdrawal
        self.assertEqual(mock_approve.call_count, 2)
        mock_approve.assert_any_call(self.withdrawal.id, self.admin_user)
        mock_approve.assert_any_call(withdrawal2.id, self.admin_user)
    
    @patch('wallets.services.WalletService.reject_withdrawal')
    def test_reject_selected_action(self, mock_reject):
        """Test reject_selected admin action"""
        withdrawal2 = WithdrawalRequest.objects.create(
            user=self.other_user,
            amount=Decimal('75.00'),
            withdrawal_method='bank_transfer',
            account_number='0987654321',
            account_name='Other Account',
            bank_name='Other Bank',
            status='pending'
        )
        
        # Mock successful rejection
        mock_reject.return_value = None
        
        mock_request = Mock()
        mock_request.user = self.admin_user
        
        queryset = WithdrawalRequest.objects.filter(status='pending')
        
        # Execute action
        self.withdrawal_admin.reject_selected(mock_request, queryset)
        
        # Should call reject for each pending withdrawal
        self.assertEqual(mock_reject.call_count, 2)
        mock_reject.assert_any_call(self.withdrawal.id, self.admin_user, "Bulk rejection")
        mock_reject.assert_any_call(withdrawal2.id, self.admin_user, "Bulk rejection")
    
    def test_list_filter_configuration(self):
        """Test list filter configuration"""
        expected_filters = ['status', 'withdrawal_method', 'created_at']
        self.assertEqual(list(self.withdrawal_admin.list_filter), expected_filters)
    
    def test_search_fields_configuration(self):
        """Test search fields configuration"""
        expected_search = ['user__username', 'account_name', 'bank_name']
        self.assertEqual(list(self.withdrawal_admin.search_fields), expected_search)


class AdminIntegrationTest(WalletTestCase):
    """Test admin interface integration"""
    
    def setUp(self):
        super().setUp()
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)
    
    def test_wallet_admin_changelist_view(self):
        """Test wallet admin changelist view"""
        url = reverse('admin:wallets_wallet_changelist')
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
    
    def test_transaction_admin_changelist_view(self):
        """Test transaction admin changelist view"""
        # Create transaction for testing
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00')
        )
        
        url = reverse('admin:wallets_transaction_changelist')
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, '100.00')
    
    def test_withdrawal_admin_changelist_view(self):
        """Test withdrawal admin changelist view"""
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('200.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
        
        url = reverse('admin:wallets_withdrawalrequest_changelist')
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, '200.00')
    
    def test_escrow_admin_changelist_view(self):
        """Test escrow admin changelist view"""
        task = self.create_task(self.user, "Admin Integration Test Task")
        EscrowTransaction.objects.create(
            task=task,
            advertiser=self.user,
            amount=Decimal('150.00'),
            status='locked'
        )
        
        url = reverse('admin:wallets_escrowtransaction_changelist')
        response = self.admin_client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Integration Test Task')
        self.assertContains(response, '150.00')
    
    def test_admin_permissions_non_staff(self):
        """Test that non-staff users cannot access admin"""
        client = Client()
        client.force_login(self.user)  # Regular user, not staff
        
        url = reverse('admin:wallets_wallet_changelist')
        response = client.get(url)
        
        # Should redirect to login or show permission denied
        self.assertIn(response.status_code, [302, 403])
    
    def test_admin_search_functionality(self):
        """Test admin search functionality"""
        # Create transaction with searchable content
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00'),
            reference='SEARCH_TEST_REF',
            description='Searchable description content'
        )
        
        url = reverse('admin:wallets_transaction_changelist')
        
        # Search by username
        response = self.admin_client.get(url, {'q': self.user.username})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        
        # Search by reference
        response = self.admin_client.get(url, {'q': 'SEARCH_TEST_REF'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SEARCH_TEST_REF')
        
        # Search by description
        response = self.admin_client.get(url, {'q': 'Searchable description'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Searchable description')
    
    def test_admin_filtering_functionality(self):
        """Test admin filtering functionality"""
        # Create transactions with different types
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00')
        )
        
        Transaction.objects.create(
            user=self.user,
            transaction_type='debit',
            category='withdrawal',
            amount=Decimal('50.00'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('50.00')
        )
        
        url = reverse('admin:wallets_transaction_changelist')
        
        # Filter by credit transactions
        response = self.admin_client.get(url, {'transaction_type__exact': 'credit'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'credit')
        
        # Filter by debit transactions
        response = self.admin_client.get(url, {'transaction_type__exact': 'debit'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'debit')