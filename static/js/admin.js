/**
 * Ptah Studios - Admin JavaScript
 * Dashboard Management Functionality
 */

(function() {
    'use strict';
    
    // ===========================
    // Utility Functions
    // ===========================
    
    const $ = (selector, context = document) => context.querySelector(selector);
    const $$ = (selector, context = document) => Array.from(context.querySelectorAll(selector));
    
    const addClass = (element, className) => element.classList.add(className);
    const removeClass = (element, className) => element.classList.remove(className);
    const toggleClass = (element, className) => element.classList.toggle(className);
    
    const on = (element, event, handler, options) => {
        element.addEventListener(event, handler, options);
        return () => element.removeEventListener(event, handler, options);
    };
    
    const debounce = (func, wait) => {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };
    
    // ===========================
    // Sidebar Toggle
    // ===========================
    
    const initSidebar = () => {
        const sidebarToggle = $('#sidebarToggle');
        const sidebar = $('.admin-sidebar');
        
        if (sidebarToggle && sidebar) {
            on(sidebarToggle, 'click', () => {
                toggleClass(sidebar, 'open');
            });
            
            // Close sidebar when clicking outside on mobile
            on(document, 'click', (e) => {
                if (window.innerWidth <= 1024 &&
                    !sidebar.contains(e.target) &&
                    !sidebarToggle.contains(e.target) &&
                    hasClass(sidebar, 'open')) {
                    removeClass(sidebar, 'open');
                }
            });
        }
    };
    
    // ===========================
    // Flash Messages
    // ===========================
    
    const initFlashMessages = () => {
        $$('.flash-close').forEach(button => {
            on(button, 'click', (e) => {
                const message = e.target.closest('.flash-message');
                if (message) {
                    message.style.animation = 'fadeOut 0.3s ease-out forwards';
                    setTimeout(() => message.remove(), 300);
                }
            });
        });
        
        // Auto-dismiss after 5 seconds
        $$('.flash-message').forEach(message => {
            setTimeout(() => {
                message.style.animation = 'fadeOut 0.3s ease-out forwards';
                setTimeout(() => message.remove(), 300);
            }, 5000);
        });
    };
    
    // ===========================
    // Status Selects
    // ===========================
    
    const initStatusSelects = () => {
        $$('.status-select').forEach(select => {
            on(select, 'change', function() {
                this.form.submit();
            });
        });
    };
    
    // ===========================
    // Table Row Actions
    // ===========================
    
    const initTableActions = () => {
        // Add hover effect for table rows
        $$('.admin-table tbody tr').forEach(row => {
            on(row, 'click', (e) => {
                // Only trigger if not clicking on a form element
                if (e.target.tagName !== 'INPUT' && 
                    e.target.tagName !== 'SELECT' && 
                    e.target.tagName !== 'BUTTON' &&
                    !e.target.closest('form')) {
                    const viewLink = $('a[href*="client_id"], a[href*="project_id"]', row);
                    if (viewLink) {
                        window.location.href = viewLink.href;
                    }
                }
            });
        });
    };
    
    // ===========================
    // Project Card Interactions
    // ===========================
    
    const initProjectCards = () => {
        $$('.project-card').forEach(card => {
            on(card, 'click', (e) => {
                // Don't navigate if clicking on specific interactive elements
                if (e.target.tagName === 'SELECT' || 
                    e.target.closest('.status-badge')) {
                    return;
                }
            });
            
            // Add ripple effect on click
            on(card, 'click', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const ripple = document.createElement('span');
                ripple.style.cssText = `
                    position: absolute;
                    background: rgba(212, 175, 55, 0.3);
                    border-radius: 50%;
                    pointer-events: none;
                    transform: scale(0);
                    animation: ripple 0.6s ease-out;
                    width: 100px;
                    height: 100px;
                    left: ${x - 50}px;
                    top: ${y - 50}px;
                `;
                
                card.style.position = 'relative';
                card.style.overflow = 'hidden';
                card.appendChild(ripple);
                
                setTimeout(() => ripple.remove(), 600);
            });
        });
    };
    
    // ===========================
    // Quick Actions
    // ===========================
    
    const initQuickActions = () => {
        $$('.quick-action').forEach(action => {
            on(action, 'click', (e) => {
                const href = action.getAttribute('href');
                if (href && !href.startsWith('#')) {
                    // Add loading state
                    addClass(action, 'loading');
                    action.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                }
            });
        });
    };
    
    // ===========================
    // Search Functionality
    // ===========================
    
    const initSearch = () => {
        const searchForm = $('.search-form');
        const searchInput = $('.search-input', searchForm);
        
        if (searchInput && searchForm) {
            // Clear search functionality
            on(searchForm, 'submit', (e) => {
                if (!searchInput.value.trim()) {
                    e.preventDefault();
                    window.location.href = window.location.pathname;
                }
            });
        }
    };
    
    // ===========================
    // Task Checkbox
    // ===========================
    
    const initTaskList = () => {
        $$('.task-item').forEach(task => {
            on(task, 'click', (e) => {
                const checkbox = $('.check-link', task);
                if (checkbox && !hasClass(task, 'completed')) {
                    window.location.href = checkbox.href;
                }
            });
        });
    };
    
    // ===========================
    // Range Input
    // ===========================
    
    const initRangeInputs = () => {
        $$('.range-input').forEach(input => {
            const valueDisplay = input.parentElement.querySelector('.stat-value') || 
                                 input.parentElement.querySelector('.progress-header span:last-child');
            
            if (valueDisplay) {
                on(input, 'input', () => {
                    valueDisplay.textContent = input.value + '%';
                });
            }
        });
    };
    
    // ===========================
    // Initialize Everything
    // ===========================
    
    const init = () => {
        initSidebar();
        initFlashMessages();
        initStatusSelects();
        initTableActions();
        initProjectCards();
        initQuickActions();
        initSearch();
        initTaskList();
        initRangeInputs();
        
        console.log('%c Ptah Studios Admin ', 'background: #0A192F; color: #D4AF37; font-size: 16px; padding: 8px;');
        console.log('%c Dashboard Loaded ', 'color: #0A192F; font-size: 11px;');
    };
    
    // Add ripple animation styles
    const style = document.createElement('style');
    style.textContent = `
        @keyframes ripple {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
        @keyframes fadeOut {
            to {
                opacity: 0;
                transform: translateX(100%);
            }
        }
        .quick-action.loading {
            pointer-events: none;
            opacity: 0.7;
        }
        .animate-ready {
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.5s ease-out;
        }
        .animate-ready.animate-in {
            opacity: 1;
            transform: translateY(0);
        }
    `;
    document.head.appendChild(style);
    
    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();
