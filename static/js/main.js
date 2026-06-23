/**
 * Ptah Studios - Main JavaScript
 * Immersive Awwards-Winning Experience
 */

(function() {
    'use strict';
    
    // ===========================
    // Utility Functions
    // ===========================
    
    const $ = (selector, context = document) => {
        try {
            return context.querySelector(selector);
        } catch (e) {
            console.warn('Invalid selector:', selector);
            return null;
        }
    };
    
    const $$ = (selector, context = document) => {
        try {
            return Array.from(context.querySelectorAll(selector));
        } catch (e) {
            console.warn('Invalid selector:', selector);
            return [];
        }
    };
    
    const addClass = (element, className) => {
        if (element && className) {
            element.classList.add(className);
        }
    };
    
    const removeClass = (element, className) => {
        if (element && className) {
            element.classList.remove(className);
        }
    };
    
    const toggleClass = (element, className) => {
        if (element && className) {
            element.classList.toggle(className);
        }
    };
    
    const hasClass = (element, className) => {
        return element && className && element.classList.contains(className);
    };
    
    const on = (element, event, handler, options) => {
        if (element && typeof element.addEventListener === 'function') {
            element.addEventListener(event, handler, options);
        }
        return () => {
            if (element && typeof element.removeEventListener === 'function') {
                element.removeEventListener(event, handler, options);
            }
        };
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
    
    const formatCurrency = (amount, currency = 'USD') => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency,
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    };
    
    // Check for reduced motion preference
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    // ===========================
    // Custom Cursor - "Divine Spark"
    // ===========================
    
    const initCustomCursor = () => {
        if (prefersReducedMotion) return;
        
        let cursor = $('.cursor');
        let cursorTrail = $('.cursor-trail');
        
        if (!cursor) {
            cursor = document.createElement('div');
            cursor.className = 'cursor';
            document.body.appendChild(cursor);
        }
        
        if (!cursorTrail) {
            cursorTrail = document.createElement('div');
            cursorTrail.className = 'cursor-trail';
            document.body.appendChild(cursorTrail);
        }
        
        let mouseX = window.innerWidth / 2;
        let mouseY = window.innerHeight / 2;
        let cursorX = mouseX;
        let cursorY = mouseY;
        let trailX = mouseX;
        let trailY = mouseY;
        
        const handleMouseMove = (e) => {
            mouseX = e.clientX;
            mouseY = e.clientY;
        };
        
        document.addEventListener('mousemove', handleMouseMove);
        
        const animateCursor = () => {
            cursorX += (mouseX - cursorX) * 0.15;
            cursorY += (mouseY - cursorY) * 0.15;
            
            cursor.style.transform = `translate(${cursorX - 5}px, ${cursorY - 5}px)`;
            
            trailX += (mouseX - trailX) * 0.08;
            trailY += (mouseY - trailY) * 0.08;
            
            cursorTrail.style.transform = `translate(${trailX - 20}px, ${trailY - 20}px)`;
            
            requestAnimationFrame(animateCursor);
        };
        
        animateCursor();
        
        // Hover effects on interactive elements
        const interactiveElements = $$('a, button, .portfolio-item, .service-card, .pricing-card, .btn, .faq-item, .included-item, .process-step, .testimonial-card, .magnetic-wrap');
        
        interactiveElements.forEach(el => {
            el.addEventListener('mouseenter', () => addClass(cursor, 'hover'));
            el.addEventListener('mouseleave', () => removeClass(cursor, 'hover'));
        });
    };
    
    // ===========================
    // Three.js Particle System
    // ===========================
    
    const initParticleSystem = (canvasId) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || prefersReducedMotion) return;
        
        const THREE = window.THREE;
        if (!THREE) {
            console.warn('Three.js not loaded');
            return;
        }
        
        try {
            const scene = new THREE.Scene();
            const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
            const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
            
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            
            // Create particles
            const particleCount = canvasId === 'particle-canvas' ? 5000 : 2000;
            const geometry = new THREE.BufferGeometry();
            const positions = new Float32Array(particleCount * 3);
            const colors = new Float32Array(particleCount * 3);
            
            const goldColor = new THREE.Color(0xD4AF37);
            const navyColor = new THREE.Color(0x0A192F);
            
            for (let i = 0; i < particleCount; i++) {
                const i3 = i * 3;
                positions[i3] = (Math.random() - 0.5) * (canvasId === 'particle-canvas' ? 10 : 6);
                positions[i3 + 1] = (Math.random() - 0.5) * (canvasId === 'particle-canvas' ? 10 : 6);
                positions[i3 + 2] = (Math.random() - 0.5) * (canvasId === 'particle-canvas' ? 10 : 6);
                
                const mixFactor = Math.random();
                const color = goldColor.clone().lerp(navyColor, mixFactor);
                colors[i3] = color.r;
                colors[i3 + 1] = color.g;
                colors[i3 + 2] = color.b;
            }
            
            geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            
            const material = new THREE.PointsMaterial({
                size: canvasId === 'particle-canvas' ? 0.02 : 0.015,
                vertexColors: true,
                transparent: true,
                opacity: 0.8,
                blending: THREE.AdditiveBlending
            });
            
            const particles = new THREE.Points(geometry, material);
            scene.add(particles);
            camera.position.z = canvasId === 'particle-canvas' ? 3 : 4;
            
            let mouseX = 0;
            let mouseY = 0;
            let targetX = 0;
            let targetY = 0;
            
            const handleMouseMove = (e) => {
                mouseX = (e.clientX / window.innerWidth) * 2 - 1;
                mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
            };
            
            document.addEventListener('mousemove', handleMouseMove);
            
            const animate = () => {
                requestAnimationFrame(animate);
                
                targetX += (mouseX - targetX) * 0.02;
                targetY += (mouseY - targetY) * 0.02;
                
                particles.rotation.x += 0.001 + targetY * 0.005;
                particles.rotation.y += 0.002 + targetX * 0.005;
                
                // Gentle floating animation
                const time = Date.now() * 0.001;
                particles.position.y = Math.sin(time * 0.5) * 0.1;
                
                renderer.render(scene, camera);
            };
            
            animate();
            
            const handleResize = () => {
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            };
            
            window.addEventListener('resize', handleResize);
        } catch (e) {
            console.error('Error initializing particle system:', e);
        }
    };
    
    // Initialize all particle canvases
    const initAllParticleSystems = () => {
        const canvasIds = ['particle-canvas', 'page-particles', 'cta-particles'];
        canvasIds.forEach(id => initParticleSystem(id));
    };
    
    // ===========================
    // GSAP Animations
    // ===========================
    
    const initGSAPAnimations = () => {
        if (prefersReducedMotion) return;
        
        const GSAP = window.GSAP;
        const ScrollTrigger = window.ScrollTrigger;
        
        if (GSAP) GSAP.registerPlugin(ScrollTrigger);
        
        // Hero text animation on load
        const heroTitle = document.querySelector('.hero-title');
        if (heroTitle && GSAP) {
            const words = heroTitle.querySelectorAll('.word');
            
            GSAP.fromTo(words,
                { opacity: 0, y: 100, rotationX: -90 },
                {
                    opacity: 1,
                    y: 0,
                    rotationX: 0,
                    stagger: 0.15,
                    duration: 1.2,
                    ease: 'power4.out'
                }
            );
            
            const heroBadge = document.querySelector('.hero-badge');
            const heroText = document.querySelector('.hero-text');
            const heroActions = document.querySelector('.hero-actions');
            const heroImage = document.querySelector('.hero-image-container');
            
            if (heroBadge) {
                GSAP.fromTo(heroBadge,
                    { opacity: 0, y: 30 },
                    { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out', delay: 0.5 }
                );
            }
            
            if (heroText) {
                GSAP.fromTo(heroText,
                    { opacity: 0, y: 30 },
                    { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out', delay: 0.8 }
                );
            }
            
            if (heroActions) {
                GSAP.fromTo(heroActions,
                    { opacity: 0, y: 30 },
                    { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out', delay: 1 }
                );
            }
            
            if (heroImage) {
                GSAP.fromTo(heroImage,
                    { opacity: 0, scale: 0.9 },
                    { opacity: 1, scale: 1, duration: 1, ease: 'power3.out', delay: 0.3 }
                );
            }
        }
        
        // Services horizontal scroll with ScrollTrigger
        const servicesSection = document.querySelector('.services-section');
        if (servicesSection && ScrollTrigger && GSAP) {
            const container = servicesSection.querySelector('.services-container') || servicesSection.querySelector('.services-grid');
            const cards = servicesSection.querySelectorAll('.service-card');
            
            if (container && cards.length > 0) {
                const totalWidth = container.scrollWidth;
                const viewportWidth = window.innerWidth;
                
                if (totalWidth > viewportWidth) {
                    GSAP.to(container, {
                        x: () => -(totalWidth - viewportWidth + 128),
                        ease: 'none',
                        scrollTrigger: {
                            trigger: servicesSection,
                            start: 'top top',
                            end: () => `+=${totalWidth - viewportWidth + 200}`,
                            pin: true,
                            scrub: 1,
                            invalidateOnRefresh: true
                        }
                    });
                }
            }
        }
        
        // Golden Thread animation for Process section
        const processSection = document.querySelector('.process-section');
        if (processSection) {
            const threadProgress = processSection.querySelector('.thread-progress');
            const steps = processSection.querySelectorAll('.process-step');
            
            if (threadProgress && ScrollTrigger) {
                const pathLength = threadProgress.getTotalLength ? threadProgress.getTotalLength() : 1000;
                threadProgress.style.strokeDasharray = pathLength;
                threadProgress.style.strokeDashoffset = pathLength;
                
                ScrollTrigger.create({
                    trigger: processSection,
                    start: 'top center',
                    end: 'bottom center',
                    scrub: 1,
                    onUpdate: (self) => {
                        threadProgress.style.strokeDashoffset = pathLength - self.progress * pathLength;
                    }
                });
            }
            
            steps.forEach((step, index) => {
                if (ScrollTrigger) {
                    ScrollTrigger.create({
                        trigger: step,
                        start: 'top 75%',
                        onEnter: () => {
                            addClass(step, 'active');
                            if (!prefersReducedMotion && GSAP) {
                                GSAP.to(step, {
                                    opacity: 1,
                                    y: 0,
                                    duration: 0.6,
                                    ease: 'power3.out'
                                });
                            }
                        },
                        onLeaveBack: () => {
                            removeClass(step, 'active');
                        }
                    });
                }
            });
        }
        
        // Stats counter animation
        const initStatsCounter = () => {
            const statNumbers = document.querySelectorAll('.stat-number[data-count]');
            
            statNumbers.forEach(stat => {
                const target = parseInt(stat.dataset.count);
                
                if (ScrollTrigger) {
                    ScrollTrigger.create({
                        trigger: stat,
                        start: 'top 80%',
                        onEnter: () => {
                            let current = 0;
                            const increment = target / 60;
                            const timer = setInterval(() => {
                                current += increment;
                                if (current >= target) {
                                    stat.textContent = target + '+';
                                    clearInterval(timer);
                                } else {
                                    stat.textContent = Math.floor(current);
                                }
                            }, 30);
                        }
                    });
                }
            });
        };
        initStatsCounter();
        
        // Testimonials horizontal scroll
        const testimonialsSection = document.querySelector('.testimonials-section');
        if (testimonialsSection && ScrollTrigger && GSAP) {
            const track = testimonialsSection.querySelector('.testimonials-track');
            const cards = testimonialsSection.querySelectorAll('.testimonial-card');
            
            if (track && cards.length > 0) {
                const totalWidth = track.scrollWidth;
                const viewportWidth = window.innerWidth;
                
                if (totalWidth > viewportWidth) {
                    GSAP.to(track, {
                        x: () => -(totalWidth - viewportWidth + 100),
                        ease: 'none',
                        scrollTrigger: {
                            trigger: testimonialsSection,
                            start: 'top top',
                            end: () => `+=${totalWidth - viewportWidth}`,
                            pin: true,
                            scrub: 1,
                            invalidateOnRefresh: true
                        }
                    });
                }
            }
        }
        
        // Fade in elements on scroll
        const animatedElements = document.querySelectorAll('.service-card, .portfolio-item, .process-step, .included-item, .faq-item, .pricing-card, .testimonial-card, .contact-item, .hours-item');
        
        animatedElements.forEach(el => {
            addClass(el, 'animate-ready');
        });
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    addClass(entry.target, 'animate-in');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
        
        animatedElements.forEach(el => {
            observer.observe(el);
        });
    };
    
    // ===========================
    // WebGL Liquid Distortion
    // ===========================
    
    const initWebGLDistortion = () => {
        if (prefersReducedMotion) return;
        
        const portfolioItems = document.querySelectorAll('.portfolio-item');
        
        portfolioItems.forEach(item => {
            const img = item.querySelector('img');
            if (!img) return;
            
            const canvas = document.createElement('canvas');
            canvas.className = 'webgl-canvas';
            canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;opacity:0;transition:opacity 0.3s ease;pointer-events:none;z-index:1;';
            item.appendChild(canvas);
            
            item.addEventListener('mouseenter', () => {
                canvas.style.opacity = '1';
                initLiquidEffect(canvas, img);
            });
            
            item.addEventListener('mouseleave', () => {
                canvas.style.opacity = '0';
            });
            
            item.addEventListener('mousemove', (e) => {
                const rect = item.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                
                if (canvas.glRenderer) {
                    canvas.glRenderer.uniforms.uMouse.value = [x, y];
                    canvas.glRenderer.uniforms.uIntensity.value = 0.3;
                }
            });
        });
    };
    
    const initLiquidEffect = (canvas, img) => {
        try {
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return;
            
            canvas.width = canvas.offsetWidth * 2;
            canvas.height = canvas.offsetHeight * 2;
            gl.viewport(0, 0, canvas.width, canvas.height);
            
            const vertexShaderSource = `
                attribute vec2 a_position;
                attribute vec2 a_texCoord;
                varying vec2 v_texCoord;
                void main() {
                    gl_Position = vec4(a_position, 0, 1);
                    v_texCoord = a_texCoord;
                }
            `;
            
            const fragmentShaderSource = `
                precision mediump float;
                uniform sampler2D u_image;
                uniform vec2 u_resolution;
                uniform vec2 u_mouse;
                uniform float u_time;
                uniform float u_intensity;
                varying vec2 v_texCoord;
                
                void main() {
                    vec2 uv = v_texCoord;
                    vec2 mousePos = vec2(u_mouse.x, 1.0 - u_mouse.y);
                    float dist = distance(uv, mousePos);
                    float ripple = sin(dist * 20.0 - u_time * 3.0) * 0.02 * u_intensity;
                    vec2 distortedUV = uv + (uv - mousePos) * ripple;
                    vec4 color = texture2D(u_image, distortedUV);
                    gl_FragColor = color;
                }
            `;
            
            const createShader = (gl, type, source) => {
                const shader = gl.createShader(type);
                gl.shaderSource(shader, source);
                gl.compileShader(shader);
                return shader;
            };
            
            const createProgram = (gl, vertexShader, fragmentShader) => {
                const program = gl.createProgram();
                gl.attachShader(program, vertexShader);
                gl.attachShader(program, fragmentShader);
                gl.linkProgram(program);
                return program;
            };
            
            const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
            const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
            const program = createProgram(gl, vertexShader, fragmentShader);
            
            gl.useProgram(program);
            
            const texture = gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D, texture);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
            
            const image = new Image();
            image.src = img.src;
            image.onload = () => {
                gl.bindTexture(gl.TEXTURE_2D, texture);
                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
            };
            
            const positionBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]), gl.STATIC_DRAW);
            
            const positionLocation = gl.getAttribLocation(program, 'a_position');
            gl.enableVertexAttribArray(positionLocation);
            gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
            
            const texCoordBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0,0,1,0,0,1,0,1,1,0,1,1]), gl.STATIC_DRAW);
            
            const texCoordLocation = gl.getAttribLocation(program, 'a_texCoord');
            gl.enableVertexAttribArray(texCoordLocation);
            gl.vertexAttribPointer(texCoordLocation, 2, gl.FLOAT, false, 0, 0);
            
            const uResolution = gl.getUniformLocation(program, 'u_resolution');
            const uMouse = gl.getUniformLocation(program, 'u_mouse');
            const uTime = gl.getUniformLocation(program, 'u_time');
            const uIntensity = gl.getUniformLocation(program, 'u_intensity');
            
            gl.uniform2f(uResolution, canvas.width, canvas.height);
            gl.uniform2f(uMouse, 0.5, 0.5);
            gl.uniform1f(uIntensity, 0.0);
            
            let time = 0;
            const animate = () => {
                if (canvas.style.opacity === '0') return;
                time += 0.016;
                gl.uniform1f(uTime, time);
                gl.drawArrays(gl.TRIANGLES, 0, 6);
                requestAnimationFrame(animate);
            };
            
            animate();
            
            canvas.glRenderer = { uniforms: { uMouse, uTime, uIntensity }, program };
        } catch (e) {
            console.error('WebGL error:', e);
        }
    };
    
    // ===========================
    // Magnetic Buttons
    // ===========================
    
    const initMagneticButtons = () => {
        if (prefersReducedMotion) return;
        
        const magneticWrappers = document.querySelectorAll('.magnetic-wrap');
        
        magneticWrappers.forEach(wrapper => {
            const button = wrapper.querySelector('.btn, .btn-book, .auth-btn') || wrapper;
            
            wrapper.addEventListener('mousemove', (e) => {
                const rect = wrapper.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                
                button.style.transform = `translate(${x * 0.3}px, ${y * 0.3}px)`;
            });
            
            wrapper.addEventListener('mouseleave', () => {
                button.style.transform = 'translate(0, 0)';
            });
        });
    };
    
    // ===========================
    // Service Cards Spotlight Effect
    // ===========================
    
    const initSpotlightEffect = () => {
        const cards = document.querySelectorAll('.service-card, .pricing-card, .contact-card');
        
        cards.forEach(card => {
            let spotlight = card.querySelector('.spotlight');
            if (!spotlight) {
                spotlight = document.createElement('div');
                spotlight.className = 'spotlight';
                spotlight.style.cssText = 'position:absolute;inset:0;pointer-events:none;transition:background 0.1s ease;background:radial-gradient(circle at 50% 50%, rgba(212,175,55,0.15) 0%, transparent 50%);border-radius:inherit;z-index:0;';
                card.insertBefore(spotlight, card.firstChild);
            }
            
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                
                spotlight.style.background = `radial-gradient(circle at ${x * 100}% ${y * 100}%, rgba(212,175,55,0.12) 0%, transparent 50%)`;
            });
            
            card.addEventListener('mouseleave', () => {
                spotlight.style.background = 'radial-gradient(circle at 50% 50%, rgba(212,175,55,0.15) 0%, transparent 50%)';
            });
        });
    };
    
    // ===========================
    // Portfolio Parallax Overlay
    // ===========================
    
    const initPortfolioParallax = () => {
        const portfolioItems = document.querySelectorAll('.portfolio-item');
        
        portfolioItems.forEach(item => {
            item.addEventListener('mousemove', (e) => {
                const rect = item.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width - 0.5;
                const y = (e.clientY - rect.top) / rect.height - 0.5;
                
                const overlay = item.querySelector('.portfolio-overlay');
                if (overlay) {
                    overlay.style.background = `linear-gradient(to top, rgba(10,25,47,0.95) 0%, transparent ${50 + y * 30}%, transparent ${50 - y * 30}%, rgba(10,25,47,0.5) 100%)`;
                }
            });
        });
    };
    
    // ===========================
    // Preloader Animation
    // ===========================
    
    const initPreloader = () => {
        const preloader = document.querySelector('.preloader');
        if (!preloader) return;
        
        const logoPath = preloader.querySelector('.logo-path');
        const preloaderText = preloader.querySelector('.preloader-text');
        
        if (logoPath) {
            logoPath.style.strokeDasharray = '200';
            logoPath.style.strokeDashoffset = '200';
            
            setTimeout(() => {
                logoPath.style.transition = 'stroke-dashoffset 1.5s ease-out';
                logoPath.style.strokeDashoffset = '0';
            }, 100);
        }
        
        if (preloaderText) {
            preloaderText.style.opacity = '0';
            setTimeout(() => {
                preloaderText.style.transition = 'opacity 0.5s ease';
                preloaderText.style.opacity = '1';
            }, 800);
        }
        
        window.addEventListener('load', () => {
            setTimeout(() => {
                addClass(preloader, 'loaded');
                
                setTimeout(() => {
                    preloader.style.opacity = '0';
                    setTimeout(() => {
                        preloader.style.display = 'none';
                        initGSAPAnimations();
                    }, 500);
                }, 800);
            }, 1500);
        });
    };
    
    // ===========================
    // Mobile Navigation
    // ===========================
    
    const initMobileNav = () => {
        const header = document.querySelector('.main-header');
        if (!header) return;
        
        let menuToggle = document.querySelector('.menu-toggle');
        if (!menuToggle) {
            menuToggle = document.createElement('button');
            menuToggle.className = 'menu-toggle';
            menuToggle.innerHTML = '<span></span><span></span><span></span>';
            menuToggle.setAttribute('aria-label', 'Toggle menu');
            
            const navbar = document.querySelector('.navbar');
            if (navbar) {
                navbar.insertBefore(menuToggle, navbar.firstChild);
            }
        }
        
        const navLinks = document.querySelector('.nav-links');
        if (!navLinks) return;
        
        menuToggle.addEventListener('click', () => {
            toggleClass(menuToggle, 'active');
            toggleClass(navLinks, 'open');
            toggleClass(document.body, 'menu-open');
        });
        
        navLinks.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                removeClass(menuToggle, 'active');
                removeClass(navLinks, 'open');
                removeClass(document.body, 'menu-open');
            });
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && hasClass(navLinks, 'open')) {
                removeClass(menuToggle, 'active');
                removeClass(navLinks, 'open');
                removeClass(document.body, 'menu-open');
            }
        });
    };
    
    // ===========================
    // Header Scroll Effect
    // ===========================
    
    const initHeaderScroll = () => {
        const header = document.querySelector('.main-header');
        if (!header) return;
        
        const handleScroll = debounce(() => {
            if (window.scrollY > 50) {
                addClass(header, 'scrolled');
            } else {
                removeClass(header, 'scrolled');
            }
        }, 10);
        
        window.addEventListener('scroll', handleScroll);
    };
    
    // ===========================
    // Smooth Scroll
    // ===========================
    
    const initSmoothScroll = () => {
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href^="#"]');
            if (!link) return;
            
            const targetId = link.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (!targetElement) return;
            
            e.preventDefault();
            
            const header = document.querySelector('.main-header');
            const headerOffset = header ? header.offsetHeight + 20 : 100;
            const elementPosition = targetElement.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
            
            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        });
    };
    
    // ===========================
    // Portfolio Filtering
    // ===========================
    
    const initPortfolioFilter = () => {
        const filterButtons = document.querySelectorAll('.filter-btn');
        if (filterButtons.length === 0) return;
        
        filterButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const category = button.dataset.filter;
                
                filterButtons.forEach(btn => removeClass(btn, 'active'));
                addClass(button, 'active');
                
                const portfolioItems = document.querySelectorAll('.portfolio-item');
                portfolioItems.forEach(item => {
                    const itemCategory = item.dataset.category;
                    
                    if (category === 'all' || itemCategory === category) {
                        removeClass(item, 'hidden');
                        item.style.animation = 'fadeInUp 0.4s ease-out forwards';
                    } else {
                        addClass(item, 'hidden');
                    }
                });
            });
        });
    };
    
    // ===========================
    // Pricing Calculator
    // ===========================
    
    const initPricingCalculator = () => {
        const durationInputs = document.querySelectorAll('input[name="duration"]');
        const complexityInputs = document.querySelectorAll('input[name="complexity"]');
        const addonInputs = document.querySelectorAll('input[name="addons"]');
        
        // Exit if no calculator elements exist
        if (durationInputs.length === 0) return;
        
        const summaryBase = document.getElementById('summary-base');
        const summaryDuration = document.getElementById('summary-duration');
        const summaryTier = document.getElementById('summary-tier');
        const summaryMultiplier = document.getElementById('summary-multiplier');
        const summaryAddons = document.getElementById('summary-addons');
        const summaryTotal = document.getElementById('summary-total');
        const addonsRow = document.getElementById('addons-row');
        
        const calculateTotal = () => {
            let duration = 4;
            let pricePerHour = 200;
            let multiplier = 1.5;
            let tierName = 'Standard';
            let addonsTotal = 0;
            
            durationInputs.forEach(input => {
                if (input.checked) {
                    duration = parseInt(input.value);
                    pricePerHour = parseFloat(input.dataset.price) || 200;
                }
            });
            
            complexityInputs.forEach(input => {
                if (input.checked) {
                    multiplier = parseFloat(input.value);
                    tierName = input.dataset.name || 'Standard';
                }
            });
            
            addonInputs.forEach(input => {
                if (input.checked) addonsTotal += parseFloat(input.dataset.price) || 0;
            });
            
            const subtotal = (pricePerHour * duration * multiplier) + addonsTotal;
            
            if (summaryBase) summaryBase.textContent = formatCurrency(pricePerHour);
            if (summaryDuration) summaryDuration.textContent = duration + ' hour' + (duration > 1 ? 's' : '');
            if (summaryTier) summaryTier.textContent = tierName;
            if (summaryMultiplier) summaryMultiplier.textContent = multiplier + 'x';
            
            if (addonsTotal > 0 && addonsRow) {
                addonsRow.style.display = 'flex';
                if (summaryAddons) summaryAddons.textContent = '+' + formatCurrency(addonsTotal);
            } else if (addonsRow) {
                addonsRow.style.display = 'none';
            }
            
            if (summaryTotal) summaryTotal.textContent = formatCurrency(Math.round(subtotal));
        };
        
        durationInputs.forEach(input => input.addEventListener('change', calculateTotal));
        complexityInputs.forEach(input => input.addEventListener('change', calculateTotal));
        addonInputs.forEach(input => input.addEventListener('change', calculateTotal));
        
        calculateTotal();
    };
    
    // ===========================
    // Contact Form
    // ===========================
    
    const initContactForm = () => {
        const form = document.querySelector('.contact-form');
        if (!form) return;
        
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                addClass(submitBtn, 'loading');
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
            }
            
            setTimeout(() => {
                alert('Thank you for your message! We will get back to you within 24 hours.');
                form.reset();
                if (submitBtn) {
                    submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Send Message';
                    removeClass(submitBtn, 'loading');
                    submitBtn.disabled = false;
                }
            }, 1500);
        });
        
        // Input focus effects
        const inputs = form.querySelectorAll('.form-input, .form-textarea, .form-select');
        inputs.forEach(input => {
            input.addEventListener('focus', () => {
                addClass(input.parentElement, 'focused');
            });
            input.addEventListener('blur', () => {
                removeClass(input.parentElement, 'focused');
            });
        });
    };
    
    // ===========================
    // Register Form
    // ===========================
    
    const initRegisterForm = () => {
        const form = document.getElementById('registerForm');
        if (!form) return;
        
        const passwordInput = document.getElementById('password');
        const strengthBar = form.querySelector('.strength-bar');
        
        if (passwordInput && strengthBar) {
            passwordInput.addEventListener('input', () => {
                const password = passwordInput.value;
                let strength = 0;
                
                if (password.length >= 8) strength += 25;
                if (password.match(/[a-z])) strength += 25;
                if (password.match(/[A-Z])) strength += 25;
                if (password.match(/[0-9]/) || password.match(/[^a-zA-Z0-9]/)) strength += 25;
                
                strengthBar.style.width = strength + '%';
                
                if (strength <= 25) {
                    strengthBar.style.backgroundColor = '#e74c3c';
                } else if (strength <= 50) {
                    strengthBar.style.backgroundColor = '#f39c12';
                } else if (strength <= 75) {
                    strengthBar.style.backgroundColor = '#3498db';
                } else {
                    strengthBar.style.backgroundColor = '#27ae60';
                }
            });
        }
        
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;
            
            if (password !== confirmPassword) {
                alert('Passwords do not match');
                return;
            }
            
            if (password.length < 8) {
                alert('Password must be at least 8 characters');
                return;
            }
            
            const terms = document.getElementById('terms');
            if (terms && !terms.checked) {
                alert('Please agree to the Terms of Service and Privacy Policy');
                return;
            }
            
            alert('Account created successfully! Welcome to Ptah Studios.');
            window.location.href = 'index.html';
        });
    };
    
    // ===========================
    // FAQ Accordion
    // ===========================
    
    const initFAQAccordion = () => {
        const faqItems = document.querySelectorAll('.faq-item');
        if (faqItems.length === 0) return;
        
        faqItems.forEach(item => {
            const question = item.querySelector('h4');
            if (!question) return;
            
            const answer = item.querySelector('p');
            if (!answer) return;
            
            answer.style.maxHeight = '0';
            answer.style.overflow = 'hidden';
            answer.style.transition = 'max-height 0.3s ease';
            
            question.addEventListener('click', () => {
                const isActive = hasClass(item, 'active');
                
                faqItems.forEach(otherItem => {
                    removeClass(otherItem, 'active');
                    const otherAnswer = otherItem.querySelector('p');
                    if (otherAnswer) {
                        otherAnswer.style.maxHeight = '0';
                    }
                });
                
                if (!isActive) {
                    addClass(item, 'active');
                    answer.style.maxHeight = answer.scrollHeight + 'px';
                }
            });
        });
    };
    
    // ===========================
    // Initialize Everything
    // ===========================
    
    const init = () => {
        try {
            initCustomCursor();
            initAllParticleSystems();
            initPreloader();
            initMobileNav();
            initHeaderScroll();
            initSmoothScroll();
            initPortfolioFilter();
            initPricingCalculator();
            initContactForm();
            initRegisterForm();
            initFAQAccordion();
            initMagneticButtons();
            initSpotlightEffect();
            initPortfolioParallax();
            initWebGLDistortion();
            
            // Delay GSAP animations until after preloader
            if (!document.querySelector('.preloader')) {
                setTimeout(initGSAPAnimations, 500);
            }
            
            console.log('%c Ptah Studios ', 'background: #0A192F; color: #D4AF37; font-size: 20px; padding: 10px;');
            console.log('%c Immersive Experience Loaded ', 'color: #D4AF37; font-size: 12px;');
        } catch (e) {
            console.error('Error initializing Ptah Studios:', e);
        }
    };
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();
