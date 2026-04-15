document.addEventListener('DOMContentLoaded', () => {
    // Intersection Observer for scroll animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: "0px 0px -50px 0px"
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Apply animation class to elements
    const elementsToAnimate = [
        ...document.querySelectorAll('.fade-in-up'),
        ...document.querySelectorAll('.feature-card'),
        document.querySelector('.architecture-content'),
        document.querySelector('.architecture-visual'),
        document.querySelector('.company-box')
    ];

    elementsToAnimate.forEach((el, index) => {
        if (el && !el.classList.contains('fade-in-up')) {
            el.classList.add('fade-in-up');
            // Stagger animations slightly if they are cards
            if (el.classList.contains('feature-card')) {
                el.style.transitionDelay = `${index * 0.1}s`;
            }
        }
        if (el) {
            observer.observe(el);
        }
    });

    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#' || !targetId) return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                e.preventDefault();
                const headerOffset = 80;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
  
                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }
        });
    });
});
