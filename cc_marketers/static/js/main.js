// static/js/main.js

// DOM Content Loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize all functionality
    initializeDropdowns();
    initializeCopyButtons();
    initializeToasts();
    initializeMobileMenu();
    initializeFormValidation();
    initializeProgressBars();
});

// Dropdown functionality
function initializeDropdowns() {
    const dropdowns = document.querySelectorAll('.group');
    
    dropdowns.forEach(dropdown => {
        const button = dropdown.querySelector('button');
        const menu = dropdown.querySelector('.group-hover\\:opacity-100');
        
        if (button && menu) {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                
                // Close other dropdowns
                dropdowns.forEach(other => {
                    if (other !== dropdown) {
                        other.classList.remove('active');
                    }
                });
                
                // Toggle current dropdown
                dropdown.classList.toggle('active');
            });
        }
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', () => {
        dropdowns.forEach(dropdown => {
            dropdown.classList.remove('active');
        });
    });
}

// Copy to clipboard functionality
function initializeCopyButtons() {
    const copyButtons = document.querySelectorAll('[data-copy]');
    
    copyButtons.forEach(button => {
        button.addEventListener('click', async function() {
            const targetSelector = this.dataset.copy;
            const targetElement = document.querySelector(targetSelector);
            
            if (targetElement) {
                const textToCopy = targetElement.value || targetElement.textContent;
                
                try {
                    await navigator.clipboard.writeText(textToCopy);
                    showToast('Copied to clipboard!', 'success');
                    
                    // Visual feedback
                    const originalText = this.innerHTML;
                    this.innerHTML = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path></svg><span>Copied!</span>';
                    
                    setTimeout(() => {
                        this.innerHTML = originalText;
                    }, 2000);
                } catch (err) {
                    showToast('Failed to copy to clipboard', 'error');
                }
            }
        });
    });
    
    // Auto-detect copy buttons for referral links
    const referralInputs = document.querySelectorAll('input[value*="ref/"]');
    referralInputs.forEach(input => {
        const copyBtn = input.parentElement.querySelector('button');
        if (copyBtn && !copyBtn.hasAttribute('data-copy')) {
            copyBtn.setAttribute('data-copy', '#' + input.id);
        }
    });
}

// Toast notification system
function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast ${getToastClasses(type)}`;
    
    const icon = getToastIcon(type);
    toast.innerHTML = `
        <div class="flex items-center space-x-2">
            ${icon}
            <span class="font-medium">${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-current hover:opacity-75">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Auto remove after duration
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, duration);
}

function getToastClasses(type) {
    const classes = {
        success: 'border-green-200 text-green-800 bg-green-50',
        error: 'border-red-200 text-red-800 bg-red-50',
        warning: 'border-yellow-200 text-yellow-800 bg-yellow-50',
        info: 'border-red-200 text-red-800 bg-red-50'
    };
    return classes[type] || classes.info;
}

function getToastIcon(type) {
    const icons = {
        success: '<svg class="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>',
        error: '<svg class="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>',
        warning: '<svg class="w-5 h-5 text-yellow-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>',
        info: '<svg class="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>'
    };
    return icons[type] || icons.info;
}

function initializeToasts() {
    // Auto-show Django messages as toasts
    const djangoMessages = document.querySelectorAll('.django-message');
    djangoMessages.forEach(message => {
        const type = message.dataset.level;
        const text = message.textContent;
        showToast(text, type);
        message.remove();
    });
}

// Mobile menu functionality
function initializeMobileMenu() {
    const mobileMenuButton = document.querySelector('[data-mobile-menu]');
    const mobileMenu = document.querySelector('[data-mobile-menu-content]');
    
    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
            
            // Update button icon
            const openIcon = mobileMenuButton.querySelector('.menu-open');
            const closeIcon = mobileMenuButton.querySelector('.menu-close');
            
            if (openIcon && closeIcon) {
                openIcon.classList.toggle('hidden');
                closeIcon.classList.toggle('hidden');
            }
        });
        
        // Close mobile menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!mobileMenuButton.contains(e.target) && !mobileMenu.contains(e.target)) {
                mobileMenu.classList.add('hidden');
            }
        });
    }
}

// Form validation
function initializeFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            // Real-time validation
            input.addEventListener('blur', () => validateField(input));
            input.addEventListener('input', () => clearFieldError(input));
        });
        
        // Form submission validation
        form.addEventListener('submit', (e) => {
            let isValid = true;
            
            inputs.forEach(input => {
                if (!validateField(input)) {
                    isValid = false;
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                showToast('Please correct the errors below', 'error');
            }
        });
    });
}

function validateField(field) {
    const value = field.value.trim();
    const type = field.type;
    const required = field.required;
    
    clearFieldError(field);
    
    if (required && !value) {
        showFieldError(field, 'This field is required');
        return false;
    }
    
    if (value) {
        switch (type) {
            case 'email':
                if (!isValidEmail(value)) {
                    showFieldError(field, 'Please enter a valid email address');
                    return false;
                }
                break;
            case 'password':
                if (field.name === 'password1' && value.length < 8) {
                    showFieldError(field, 'Password must be at least 8 characters long');
                    return false;
                }
                break;
            case 'tel':
                if (!isValidPhone(value)) {
                    showFieldError(field, 'Please enter a valid phone number');
                    return false;
                }
                break;
        }
        
        // Password confirmation
        if (field.name === 'password2') {
            const password1 = document.querySelector('input[name="password1"]');
            if (password1 && value !== password1.value) {
                showFieldError(field, 'Passwords do not match');
                return false;
            }
        }
    }
    
    return true;
}

function showFieldError(field, message) {
    field.classList.add('border-red-500', 'ring-red-500');
    field.classList.remove('border-red-300');
    
    let errorElement = field.parentElement.querySelector('.field-error');
    if (!errorElement) {
        errorElement = document.createElement('p');
        errorElement.className = 'field-error text-red-600 text-sm mt-1';
        field.parentElement.appendChild(errorElement);
    }
    errorElement.textContent = message;
}

function clearFieldError(field) {
    field.classList.remove('border-red-500', 'ring-red-500');
    field.classList.add('border-red-300');
    
    const errorElement = field.parentElement.querySelector('.field-error');
    if (errorElement) {
        errorElement.remove();
    }
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function isValidPhone(phone) {
    const phoneRegex = /^[\+]?[1-9][\d]{0,15}$/;
    return phoneRegex.test(phone.replace(/\s/g, ''));
}

// Progress bar animations
function initializeProgressBars() {
    const progressBars = document.querySelectorAll('.progress-fill');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const progressBar = entry.target;
                const targetWidth = progressBar.dataset.progress || '0';
                
                progressBar.style.width = '0%';
                setTimeout(() => {
                    progressBar.style.width = targetWidth + '%';
                }, 100);
            }
        });
    });
    
    progressBars.forEach(bar => observer.observe(bar));
}

// Utility functions
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-NG', {
        style: 'currency',
        currency: 'NGN'
    }).format(amount);
}

function formatDate(date) {
    return new Intl.DateTimeFormat('en-NG', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    }).format(new Date(date));
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Loading state management
function showLoading(element) {
    const originalContent = element.innerHTML;
    element.dataset.originalContent = originalContent;
    element.innerHTML = '<div class="spinner"></div>';
    element.disabled = true;
}

function hideLoading(element) {
    const originalContent = element.dataset.originalContent;
    if (originalContent) {
        element.innerHTML = originalContent;
        delete element.dataset.originalContent;
    }
    element.disabled = false;
}

// Export functions for global use
window.CC_Marketers = {
    showToast,
    showLoading,
    hideLoading,
    formatCurrency,
    formatDate,
    debounce
};
