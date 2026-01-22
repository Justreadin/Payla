// Privacy Policy Page JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Theme Toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            document.body.classList.toggle('light-theme');
            
            const icon = this.querySelector('i');
            if (document.body.classList.contains('light-theme')) {
                icon.className = 'fas fa-sun';
                localStorage.setItem('privacy-theme', 'light');
            } else {
                icon.className = 'fas fa-moon';
                localStorage.setItem('privacy-theme', 'dark');
            }
        });

        // Load saved theme
        const savedTheme = localStorage.getItem('privacy-theme') || localStorage.getItem('theme');
        if (savedTheme === 'light') {
            document.body.classList.add('light-theme');
            themeToggle.querySelector('i').className = 'fas fa-sun';
        }
    }

    // Mobile Navigation Toggle
    const navToggle = document.getElementById('nav-toggle');
    const quickNav = document.getElementById('quick-nav');
    
    if (navToggle && quickNav) {
        navToggle.addEventListener('click', function() {
            quickNav.classList.toggle('expanded');
            const icon = this.querySelector('i');
            if (quickNav.classList.contains('expanded')) {
                icon.className = 'fas fa-times';
            } else {
                icon.className = 'fas fa-bars';
            }
        });
    }

    // Scroll to Top Button
    const scrollTopBtn = document.getElementById('scroll-top');
    if (scrollTopBtn) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                scrollTopBtn.classList.add('visible');
            } else {
                scrollTopBtn.classList.remove('visible');
            }
        });

        scrollTopBtn.addEventListener('click', function() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                e.preventDefault();
                
                // Close mobile nav if open
                if (quickNav && quickNav.classList.contains('expanded')) {
                    quickNav.classList.remove('expanded');
                    if (navToggle) {
                        navToggle.querySelector('i').className = 'fas fa-bars';
                    }
                }
                
                // Scroll to target
                const headerOffset = 100;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });

    // Add scroll progress indicator
    const progressBar = document.createElement('div');
    progressBar.className = 'scroll-progress';
    progressBar.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--rose-gold), var(--gold-dust));
        width: 0%;
        z-index: 1001;
        transition: width 0.3s ease;
    `;
    document.body.appendChild(progressBar);

    window.addEventListener('scroll', () => {
        const windowHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (window.pageYOffset / windowHeight) * 100;
        progressBar.style.width = `${scrolled}%`;
    });

    // Highlight current section in navigation
    const sections = document.querySelectorAll('.privacy-section');
    const navItems = document.querySelectorAll('.nav-item');
    
    function highlightSection() {
        let current = '';
        
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            
            if (scrollY >= (sectionTop - 200)) {
                const id = section.querySelector('.section-header').id;
                if (id) current = '#' + id;
            }
        });
        
        navItems.forEach(item => {
            item.classList.remove('active');
            if (item.getAttribute('href') === current) {
                item.classList.add('active');
                item.style.background = 'rgba(232, 180, 184, 0.15)';
                item.style.borderColor = 'var(--rose-gold)';
            }
        });
    }
    
    window.addEventListener('scroll', highlightSection);

    // Add hover effects to interactive elements
    const interactiveCards = document.querySelectorAll('.collection-category, .flow-item, .partner-item, .cookie-type, .security-item, .right-item, .retention-item');
    interactiveCards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = card.style.transform.replace('translateY(-2px)', 'translateY(-4px)') || 'translateY(-4px)';
            card.style.boxShadow = '0 12px 32px rgba(232, 180, 184, 0.15)';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = card.style.transform.replace('translateY(-4px)', 'translateY(-2px)') || '';
            card.style.boxShadow = '';
        });
    });

    // Add print functionality
    const printButton = document.createElement('button');
    printButton.className = 'nav-btn';
    printButton.innerHTML = '<i class="fas fa-print"></i> Print';
    printButton.addEventListener('click', () => window.print());
    
    if (document.querySelector('.nav-actions')) {
        document.querySelector('.nav-actions').appendChild(printButton);
    }

    // Add reading time estimation
    function calculateReadingTime() {
        const text = document.querySelector('.privacy-container').innerText;
        const wordCount = text.split(/\s+/).length;
        const readingTime = Math.ceil(wordCount / 200); // 200 wpm
        
        const readingTimeElement = document.createElement('div');
        readingTimeElement.className = 'meta-item';
        readingTimeElement.innerHTML = `
            <i class="fas fa-clock"></i>
            Est. reading time: ${readingTime} min
        `;
        
        const heroMeta = document.querySelector('.hero-meta');
        if (heroMeta) {
            heroMeta.appendChild(readingTimeElement);
        }
    }
    
    calculateReadingTime();

    // Mobile menu close on click outside
    document.addEventListener('click', (e) => {
        if (quickNav && quickNav.classList.contains('expanded') && 
            !quickNav.contains(e.target) && 
            e.target !== navToggle) {
            quickNav.classList.remove('expanded');
            if (navToggle) {
                navToggle.querySelector('i').className = 'fas fa-bars';
            }
        }
    });

    // Add keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && quickNav && quickNav.classList.contains('expanded')) {
            quickNav.classList.remove('expanded');
            if (navToggle) {
                navToggle.querySelector('i').className = 'fas fa-bars';
            }
        }
    });

    // Initialize section animations
    const sectionNumbers = document.querySelectorAll('.section-number');
    sectionNumbers.forEach((number, index) => {
        number.style.animationDelay = `${index * 0.1}s`;
        number.classList.add('animated');
    });
});