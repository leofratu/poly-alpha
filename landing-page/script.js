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

    // Apply fade-in class to elements we want to animate
    const elementsToAnimate = [
        ...document.querySelectorAll('.feature-card'),
        document.querySelector('.architecture-content'),
        document.querySelector('.pipeline-flow'),
        document.querySelector('.pulse-glow')
    ];

    elementsToAnimate.forEach((el, index) => {
        if (el) {
            el.classList.add('fade-in');
            // Stagger animations slightly if they are cards
            if (el.classList.contains('feature-card')) {
                el.style.transitionDelay = `${index * 0.15}s`;
            }
            observer.observe(el);
        }
    });

    // Smooth scrolling for navigation links
    document.querySelectorAll('nav a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
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
