import { useState, useRef, useEffect } from 'react';
import {
  Camera, Film, Briefcase, Gem, Heart, Rocket, Instagram, Building2,
  Trees, Coffee, Moon, Sun, Contrast, Sparkles, Dumbbell, Palette,
  Clock, Minus, Globe, Lightbulb, Crown, UserCircle, WandSparkles, Package,
  ChevronLeft, ChevronRight, ArrowRight, ArrowLeft
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// Mode configuration with icons
const ALL_MODES = [
  // Main popular modes (8)
  { value: 'studio_portrait', label: 'Studio', description: 'Clean studio portrait', fullDescription: 'Studio portrait on a plain background with soft three-point lighting. Suits portfolios and profile pages.', icon: Camera, category: 'professional' },
  { value: 'cinematic', label: 'Cinematic', description: 'Film still', fullDescription: 'A film still: dramatic light, shallow depth of field and a film colour grade.', icon: Film, category: 'creative' },
  { value: 'corporate_headshot', label: 'Corporate', description: 'Business headshot', fullDescription: 'Business headshot on a plain background with even, flattering light. Suits LinkedIn and job applications.', icon: Briefcase, category: 'professional' },
  { value: 'fashion_editorial', label: 'Fashion', description: 'Magazine editorial', fullDescription: 'Fashion magazine look with dramatic light and strong poses.', icon: Gem, category: 'creative' },
  { value: 'dating', label: 'Dating', description: 'Dating profile', fullDescription: 'Natural, warm photos for dating apps, with relaxed expressions.', icon: Heart, category: 'social' },
  { value: 'founder_headshot', label: 'Founder', description: 'Startup headshot', fullDescription: 'Confident headshot for pitch decks, investor meetings and company pages.', icon: Rocket, category: 'professional' },
  { value: 'influencer', label: 'Influencer', description: 'Social media', fullDescription: 'Bright, current look for Instagram and other social feeds.', icon: Instagram, category: 'social' },
  { value: 'street_portrait', label: 'Street', description: 'Urban portrait', fullDescription: 'Portrait on a real city street with natural light.', icon: Building2, category: 'creative' },
  // Additional modes (14)
  { value: 'environmental', label: 'Environmental', description: 'Natural setting', fullDescription: 'The person in a real-world setting with natural light.', icon: Trees, category: 'creative' },
  { value: 'lifestyle', label: 'Lifestyle', description: 'Casual moments', fullDescription: 'Candid everyday moments, relaxed and natural.', icon: Coffee, category: 'social' },
  { value: 'low_key', label: 'Low-Key', description: 'Dark and dramatic', fullDescription: 'Dark, high-contrast light with deep shadows.', icon: Moon, category: 'artistic' },
  { value: 'high_key', label: 'High-Key', description: 'Bright and airy', fullDescription: 'Bright, airy light with clean whites.', icon: Sun, category: 'artistic' },
  { value: 'black_white', label: 'B&W', description: 'Black and white', fullDescription: 'Black and white portrait with a rich tonal range.', icon: Contrast, category: 'artistic' },
  { value: 'beauty_closeup', label: 'Beauty', description: 'Close-up', fullDescription: 'Close-up with soft light that shows skin detail.', icon: Sparkles, category: 'creative' },
  { value: 'athletic', label: 'Athletic', description: 'Sport and motion', fullDescription: 'Strong stance and motion, lit like a sports shoot.', icon: Dumbbell, category: 'creative' },
  { value: 'creative_color', label: 'Creative', description: 'Bold colour', fullDescription: 'Coloured neon light and a bold colour grade.', icon: Palette, category: 'artistic' },
  { value: 'vintage_retro', label: 'Vintage', description: 'Film look', fullDescription: 'Film grain and the faded tones of old prints.', icon: Clock, category: 'artistic' },
  { value: 'minimalist', label: 'Minimalist', description: 'Simple and clean', fullDescription: 'A simple pose with plenty of empty space around it.', icon: Minus, category: 'artistic' },
  { value: 'cultural', label: 'Cultural', description: 'Heritage', fullDescription: 'Traditional clothing and heritage styling.', icon: Globe, category: 'creative' },
  { value: 'conceptual', label: 'Conceptual', description: 'Surreal', fullDescription: 'Symbolic, surreal elements that tell a story.', icon: Lightbulb, category: 'artistic' },
  { value: 'luxury', label: 'Luxury', description: 'High-end styling', fullDescription: 'High-end fashion styling with rich, soft light.', icon: Crown, category: 'creative' },
  { value: 'avatar', label: 'Avatar', description: 'Illustrated', fullDescription: 'An illustrated character version of you for profile pictures.', icon: UserCircle, category: 'artistic' },
  { value: 'restoration', label: 'Restore', description: 'Repair old photos', fullDescription: 'Repairs damage and improves the quality of old photos.', icon: WandSparkles, category: 'professional' },
  { value: 'product', label: 'Product', description: 'Packshot and scene', fullDescription: 'The exact product from your photo on a surface you pick, shape, colours and label unchanged, with soft window light and a natural contact shadow.', icon: Package, category: 'professional' },
];

interface MagixModeCarouselProps {
  selectedMode: string;
  onModeSelect: (mode: string) => void;
  onNext: () => void;
  onBack: () => void;
}

export function MagixModeCarousel({
  selectedMode,
  onModeSelect,
  onNext,
  onBack,
}: MagixModeCarouselProps) {
  const carouselRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const selectedModeData = ALL_MODES.find(m => m.value === selectedMode);

  // Check scroll position
  const checkScroll = () => {
    if (carouselRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = carouselRef.current;
      setCanScrollLeft(scrollLeft > 0);
      setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
    }
  };

  useEffect(() => {
    checkScroll();
    const carousel = carouselRef.current;
    if (carousel) {
      carousel.addEventListener('scroll', checkScroll);
      return () => carousel.removeEventListener('scroll', checkScroll);
    }
  }, []);

  const scroll = (direction: 'left' | 'right') => {
    if (carouselRef.current) {
      const scrollAmount = 320; // Card width + gap
      carouselRef.current.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth',
      });
    }
  };

  // Scroll to selected mode on mount or when selection changes
  useEffect(() => {
    if (carouselRef.current && selectedMode) {
      const selectedIndex = ALL_MODES.findIndex(m => m.value === selectedMode);
      if (selectedIndex >= 0) {
        const scrollPosition = selectedIndex * 320 - (carouselRef.current.clientWidth / 2) + 160;
        carouselRef.current.scrollTo({ left: Math.max(0, scrollPosition), behavior: 'smooth' });
      }
    }
  }, [selectedMode]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">Choose a style</h2>
        <p className="text-sm text-muted-foreground">
          {ALL_MODES.length} styles. The first edit applies the style; later edits refine it.
        </p>
      </div>

      {/* Carousel Container */}
      <div className="relative">
        {/* Left Arrow */}
        {canScrollLeft && (
          <Button
            variant="glass"
            size="icon"
            className="absolute left-0 top-1/2 -translate-y-1/2 z-10 hidden sm:flex"
            onClick={() => scroll('left')}
            aria-label="Previous styles"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        )}

        {/* Carousel */}
        <div
          ref={carouselRef}
          className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4 px-4 sm:px-8 scrollbar-hide"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {ALL_MODES.map((mode) => {
            const Icon = mode.icon;
            const isSelected = selectedMode === mode.value;

            return (
              <button
                key={mode.value}
                type="button"
                aria-pressed={isSelected}
                onClick={() => onModeSelect(mode.value)}
                className={`
                  snap-center shrink-0 w-[280px] sm:w-[300px] p-5 text-left
                  rounded-xl border bg-card transition-colors duration-150
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
                  ${isSelected
                    ? 'ring-2 ring-primary border-primary'
                    : 'border-border hover:border-foreground/20'
                  }
                `}
              >
                <div className="flex h-full flex-col">
                  <Icon className={`mb-3 h-5 w-5 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                  <h3 className="text-base font-semibold tracking-tight">{mode.label}</h3>
                  <p className="mb-2 text-xs text-muted-foreground">{mode.description}</p>
                  <p className="text-xs text-muted-foreground/80 line-clamp-2">
                    {mode.fullDescription}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right Arrow */}
        {canScrollRight && (
          <Button
            variant="glass"
            size="icon"
            className="absolute right-0 top-1/2 -translate-y-1/2 z-10 hidden sm:flex"
            onClick={() => scroll('right')}
            aria-label="More styles"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Scroll Hint (Mobile) */}
      <p className="text-center text-xs text-muted-foreground sm:hidden">
        Swipe to see more styles
      </p>

      {/* Selected Mode Info */}
      {selectedModeData && (
        <div className="max-w-2xl">
          <div className="panel rounded-xl p-5">
            <div className="flex items-start gap-3">
              <selectedModeData.icon className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
              <div>
                <h3 className="text-base font-semibold tracking-tight">Selected: {selectedModeData.label}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{selectedModeData.fullDescription}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex gap-3 justify-center">
        <Button
          variant="outline"
          size="lg"
          onClick={onBack}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <Button
          size="lg"
          onClick={onNext}
          className="min-w-[200px]"
        >
          Continue
          <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
      </div>
    </div>
  );
}
