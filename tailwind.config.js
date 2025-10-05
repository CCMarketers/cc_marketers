/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",        // global templates
    "./**/templates/**/*.html",     // per-app templates
    "./**/*.js",                    // if you use JS with Tailwind classes
    "./**/*.py"                     // for Django component libraries that generate HTML in Python
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
