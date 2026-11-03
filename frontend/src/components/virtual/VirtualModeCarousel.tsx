import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Camera, Briefcase, Sparkles, Sun, Moon, Building2,
  TreePine, PartyPopper, Dumbbell, Heart,
  ChevronLeft, ChevronRight, ArrowRight, ArrowLeft
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// Try-on style configuration
const ALL_MODES = [
  {
    value: 'natural',
    label: 'Natural',
    description: 'Realistic look',
    fullDescription: 'A natural try-on with realistic light and proportions, for everyday shopping decisions.',
    icon: Camera,
    category: 'standard',
  },
  {
    value: 'professional',
    label: 'Professional',
    description: 'Business wear',
    fullDescription: 'A polished look with studio light, for workwear and formal clothes.',
    icon: Briefcase,
    category: 'formal',
  },
  {
    value: 'glamour',
    label: 'Glamour',
    description: 'Special occasions',
    fullDescription: 'A polished look with flattering light, for special occasion outfits.',
    icon: Sparkles,
    category: 'creative',
  },
  {
    value: 'outdoor_day',
    label: 'Outdoor Day',
    description: 'Daylight outdoors',
    fullDescription: 'Outdoors in warm daylight, for casual and summer wear.',
    icon: Sun,
    category: 'outdoor',
  },
  {
    value: 'evening',
    label: 'Evening',
    description: 'Night out',
    fullDescription: 'An evening setting with soft, low light, for evening wear and formal dresses.',
    icon: Moon,
    category: 'creative',
  },
  {
    value: 'urban',
    label: 'Urban',
    description: 'City street',
    fullDescription: 'A city street backdrop, for streetwear and casual looks.',
    icon: Building2,
    category: 'outdoor',
  },
  {
    value: 'nature',
    label: 'Nature',
    description: 'Green outdoors',
    fullDescription: 'Outdoors among trees and greenery, for casual and relaxed styles.',
    icon: TreePine,
    category: 'outdoor',
  },
  {
    value: 'party',
    label: 'Party',
    description: 'Celebration',
    fullDescription: 'A party setting with colourful light, for party dresses and festive outfits.',
    icon: PartyPopper,
    category: 'creative',
  },
  {
    value: 'athletic',
    label: 'Athletic',
    description: 'Sportswear',
    fullDescription: 'A sports setting with bright light, for activewear.',
    icon: Dumbbell,
    category: 'standard',
  },
  {
    value: 'romantic',
    label: 'Romantic',
    description: 'Soft and warm',
    fullDescription: 'Soft, warm light, for date night outfits.',
    icon: Heart,
    category: 'creative',
  },
];

interface VirtualModeCarouselProps {
  selectedMode: string;
  onModeSelect: (mode: string) => void;
  onNext: () => void;
  onBack: () => void;
}

export function VirtualModeCarousel({
  selectedMode,
  onModeSelect,
  onNext,
  onBack,
}: VirtualModeCarouselProps) {
  const carouselRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const selectedModeData = ALL_MODES.find(m => m.value === selectedMode);

  // Check scroll position
  const checkScroll = useCallback(() => {
    if (carouselRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = carouselRef.current;
      setCanScrollLeft(scrollLeft > 0);
      setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
    }
  }, []);

  useEffect(() => {
    checkScroll();
    const carousel = carouselRef.current;
    if (carousel) {
      carousel.addEventListener('scroll', checkScroll);
      return () => carousel.removeEventListener('scroll', checkScroll);
    }
  }, [checkScroll]);

  const scroll = (direction: 'left' | 'right') => {
    if (carouselRef.current) {
      const scrollAmount = 320;
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
        <h2 className="text-lg font-semibold tracking-tight">Choose a setting</h2>
        <p className="text-sm text-muted-foreground">
          {ALL_MODES.length} settings for how the outfit is shown on you.
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
            aria-label="Previous settings"
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
            aria-label="More settings"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Scroll Hint (Mobile) */}
      <p className="text-center text-xs text-muted-foreground sm:hidden">
        Swipe to see more settings
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

// Export modes for use in other components
export const VIRTUAL_MODES = ALL_MODES;
