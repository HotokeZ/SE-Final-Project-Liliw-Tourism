# Liliw Tourism - Animation System Implementation Guide

## Overview
This document describes the new animation and parallax system implemented for the Liliw Tourism website, inspired by modern web design trends from sites like Fensea and Jeton.

## Files Added

### 1. CSS Files
- **`static/styles/animations.css`** - Complete animation library with:
  - Parallax background effects
  - Scroll-triggered animations
  - Hover effects
  - Fade, slide, scale, and rotate animations
  - Gradient animations
  - Particle effects
  - Wave animations

### 2. JavaScript Files
- **`static/scripts/animations.js`** - Animation controller that handles:
  - Scroll reveal animations
  - Parallax scrolling
  - Card tilt effects
  - Counter animations
  - Typewriter effects
  - Particle generation
  - Smooth scrolling
  - Button ripple effects
  - Lazy loading with fade-in
  - Stagger animations for grids

### 3. Template Includes
- **`templates/head-includes.html`** - Universal CSS includes
- **`templates/scripts-includes.html`** - Universal JavaScript includes

## Key Features

### 1. Moving Background (Parallax Effect)
The website now features a subtle, animated parallax background that moves even when scrolled:
```css
body::before {
    /* Fixed position gradient that animates */
    animation: parallaxMove 20s ease-in-out infinite;
}
```

### 2. Scroll-Triggered Animations
Elements animate into view as you scroll:
- **fade-in-up** - Fades in from bottom
- **fade-in-left** - Slides in from left
- **fade-in-right** - Slides in from right
- **scale-in** - Scales from small to full size
- **slide-in-bottom** - Slides up from bottom
- **reveal** - Generic reveal class

### 3. Hover Effects
Cards and interactive elements have smooth hover animations:
- **hover-lift** - Lifts element up on hover
- **hover-scale** - Scales element on hover
- **hover-glow** - Adds glow effect on hover
- **zoom-container** - Zooms images within

### 4. Special Effects
- **gradient-animate** - Animated gradient backgrounds
- **text-gradient** - Animated gradient text
- **pulse** - Pulsing animation
- **bounce** - Bouncing animation
- **glow** - Glowing effect
- **shimmer** - Shimmer effect

### 5. Particle Background
Subtle animated particles float across the screen for added depth.

### 6. Card Tilt Effect
Cards tilt in 3D based on mouse position (like Jeton.com).

### 7. Stagger Animations
Grid items animate in sequence with delays for visual appeal.

## How to Use in Templates

### Basic Setup (All Pages)
```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Title - Liliw Tourism</title>
    {% include 'head-includes.html' %}
    <!-- Your specific page CSS -->
</head>
<body>
    {% include 'header.html' %}

    <!-- Your content -->

    {% include 'footer.html' %}
    {% include 'scripts-includes.html' %}
</body>
```

### Add Animations to Elements

#### Hero Sections
```html
<section class="hero-section gradient-animate">
    <div class="hero-overlay">
        <div class="hero-content fade-in-up">
            <h1 class="text-gradient">Welcome</h1>
            <p>Your description</p>
        </div>
    </div>
</section>
```

#### Section Headers
```html
<div class="section-header reveal">
    <h2>Section Title</h2>
    <p class="section-subtitle">Description</p>
</div>
```

#### Cards with Stagger Effect
```html
<div class="attractions-grid">
    <div class="card stagger-1 hover-lift zoom-container">
        <img src="..." alt="...">
        <div class="card-content">
            <h3>Card Title</h3>
            <p>Description</p>
        </div>
    </div>
    <div class="card stagger-2 hover-lift zoom-container">
        <!-- More cards -->
    </div>
</div>
```

#### Buttons
```html
<a href="#" class="btn hover-scale">Click Me</a>
<button class="cta-btn hover-glow">Submit</button>
```

#### Counters (Auto-counting numbers)
```html
<div class="stat-card">
    <h3 data-count="150">0</h3>
    <p>Attractions</p>
</div>
```

#### Typewriter Effect
```html
<h2 data-typewriter="Welcome to Liliw" data-speed="100"></h2>
```

#### Parallax Elements
```html
<div data-parallax="0.5">
    <!-- This element will move slower than scroll -->
</div>
```

## Animation Classes Reference

### Entrance Animations
| Class | Effect |
|-------|--------|
| `fade-in` | Simple fade in |
| `fade-in-up` | Fade in from bottom |
| `fade-in-left` | Fade in from left |
| `fade-in-right` | Fade in from right |
| `scale-in` | Scale from small |
| `slide-in-bottom` | Slide up from bottom |
| `rotate-in` | Rotate and fade in |
| `reveal` | Scroll-triggered reveal |

### Hover Effects
| Class | Effect |
|-------|--------|
| `hover-lift` | Lifts on hover |
| `hover-scale` | Scales on hover |
| `hover-glow` | Glows on hover |
| `zoom-container` | Zoom image inside |

### Continuous Animations
| Class | Effect |
|-------|--------|
| `pulse` | Pulsing effect |
| `bounce` | Bouncing effect |
| `glow` | Glowing effect |
| `shimmer` | Shimmer effect |
| `float` | Floating effect |

### Special Effects
| Class | Effect |
|-------|--------|
| `gradient-animate` | Animated gradient |
| `text-gradient` | Gradient text |
| `wave-bg` | Wave animation |

### Timing
| Class | Delay |
|-------|-------|
| `stagger-1` | 0.1s |
| `stagger-2` | 0.2s |
| `stagger-3` | 0.3s |
| `stagger-4` | 0.4s |
| `stagger-5` | 0.5s |
| `stagger-6` | 0.6s |
| `stagger-7` | 0.7s |
| `stagger-8` | 0.8s |

## Updated Templates

The following templates have been updated with the new animation system:
- ✅ `templates/home/attractions.html` - Full animation integration
- ⏳ Other templates need manual update following the same pattern

## To Update Remaining Templates

1. Replace the `<head>` CSS includes with `{% include 'head-includes.html' %}`
2. Add animation classes to key elements (hero, sections, cards)
3. Add `{% include 'scripts-includes.html' %}` before `</body>`
4. Test animations on the page

## Performance Notes

- Animations are optimized for mobile with reduced complexity
- Respects `prefers-reduced-motion` user setting
- Uses `requestAnimationFrame` for smooth 60fps animations
- Lazy loading images with fade-in effect
- Particles are disabled on mobile for performance

## Browser Compatibility

- Modern browsers (Chrome, Firefox, Safari, Edge)
- Graceful degradation for older browsers
- Mobile-optimized animations

## Customization

To modify animation timings, edit `static/styles/animations.css`:
```css
/* Change parallax speed */
@keyframes parallaxMove {
    /* Modify keyframes */
}

/* Change animation duration */
.fade-in-up {
    animation: fadeInUp 0.8s ease-out forwards;
    /* Change 0.8s to desired duration */
}
```

To disable animations globally, add to any template:
```html
<body class="no-animation">
```

## Next Steps

1. Update remaining templates with animation classes
2. Test all pages for smooth performance
3. Adjust animation timings based on user feedback
4. Add more specialized animations as needed

## Support

For issues or questions about the animation system, refer to:
- `static/styles/animations.css` - CSS animations
- `static/scripts/animations.js` - JavaScript controllers
- This documentation file

---

**Last Updated:** December 3, 2025
**Version:** 1.0
**Created for:** Liliw Tourism Website Redesign
