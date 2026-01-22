// Terms & Conditions Page JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Set current date
    const currentDate = document.getElementById('current-date');
    if (currentDate) {
        const now = new Date();
        const options = { 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        currentDate.textContent = now.toLocaleDateString('en-US', options);
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

    // Accept Scroll Button
    const acceptScroll = document.getElementById('accept-scroll');
    if (acceptScroll) {
        acceptScroll.addEventListener('click', function() {
            const acceptanceFooter = document.querySelector('.acceptance-footer');
            acceptanceFooter.scrollIntoView({ 
                behavior: 'smooth',
                block: 'center'
            });
            
            // Add animation to acceptance section
            acceptanceFooter.classList.add('pulse');
            setTimeout(() => {
                acceptanceFooter.classList.remove('pulse');
            }, 1000);
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
                
                // Close quick nav if open on mobile
                const quickNav = document.getElementById('quick-nav');
                if (window.innerWidth < 768 && quickNav.classList.contains('expanded')) {
                    quickNav.classList.remove('expanded');
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

    // Add CSS for light theme
    const style = document.createElement('style');
    style.textContent = `
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        
        .acceptance-footer.pulse {
            animation: pulse 1s ease;
        }
    `;
    document.head.appendChild(style);

    // Section highlighting on scroll
    const sections = document.querySelectorAll('.terms-section');
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

    // Add hover effects to cards
    const cards = document.querySelectorAll('.requirement-card, .service-card, .payment-card, .ownership-card, .availability-card, .flow-step');
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-8px)';
            card.style.boxShadow = '0 20px 40px rgba(232, 180, 184, 0.15)';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(-4px)';
            card.style.boxShadow = '';
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

    // Print functionality
    const printButton = document.createElement('button');
    printButton.className = 'nav-btn';
    printButton.innerHTML = '<i class="fas fa-print"></i> Print';
    printButton.addEventListener('click', () => window.print());
    
    if (document.querySelector('.nav-actions')) {
        document.querySelector('.nav-actions').appendChild(printButton);
    }

    // Add subtle animation to section numbers
    const sectionNumbers = document.querySelectorAll('.section-number');
    sectionNumbers.forEach((number, index) => {
        number.style.animationDelay = `${index * 0.1}s`;
        number.classList.add('animated');
    });

    // Initialize tooltips for important terms
    const tooltips = {
        'AML': 'Anti-Money Laundering',
        'SaaS': 'Software-as-a-Service',
        'Third‑party': 'External service providers'
    };

    // Add tooltip functionality
    Object.keys(tooltips).forEach(term => {
        const elements = document.querySelectorAll(`:contains("${term}")`);
        elements.forEach(element => {
            if (element.textContent.includes(term) && element.tagName !== 'SCRIPT') {
                const originalText = element.innerHTML;
                const tooltipText = tooltips[term];
                element.innerHTML = originalText.replace(
                    new RegExp(`(${term})`, 'g'),
                    `<span class="term-tooltip" data-tooltip="${tooltipText}">$1</span>`
                );
            }
        });
    });

    // Add tooltip styles
    const tooltipStyle = document.createElement('style');
    tooltipStyle.textContent = `
        .term-tooltip {
            position: relative;
            color: var(--rose-gold);
            font-weight: 600;
            cursor: help;
            border-bottom: 1px dashed var(--rose-gold);
        }
        
        .term-tooltip::after {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: var(--midnight-void);
            color: var(--pearl-white);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: normal;
            white-space: nowrap;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
            border: 1px solid var(--glass-border);
            z-index: 1000;
        }
        
        .term-tooltip:hover::after {
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) translateY(-8px);
        }
    `;
    document.head.appendChild(tooltipStyle);

    // Mobile menu toggle for quick nav
    if (window.innerWidth < 768) {
        const quickNavHeader = document.querySelector('.quick-nav-header');
        if (quickNavHeader) {
            quickNavHeader.style.cursor = 'pointer';
            quickNavHeader.addEventListener('click', () => {
                const quickNav = document.getElementById('quick-nav');
                quickNav.classList.toggle('expanded');
            });
        }
    }

    // Add reading time estimation
    function calculateReadingTime() {
        const text = document.querySelector('.terms-container').innerText;
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
});