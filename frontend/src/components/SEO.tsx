interface SEOProps {
  title?: string;
  // Pages describe themselves with these. Nothing here is indexed, so they are
  // not rendered.
  description?: string;
  keywords?: string;
  image?: string;
  url?: string;
  type?: 'website' | 'article' | 'product';
  noindex?: boolean;
}

const DEFAULT_TITLE = 'Sketchmaker';

/** The tab title and a noindex tag. React 19 hoists both into the head. */
export function SEO({ title }: SEOProps) {
  return (
    <>
      <title>{title ? `${title} | ${DEFAULT_TITLE}` : DEFAULT_TITLE}</title>
      <meta name="robots" content="noindex, nofollow" />
    </>
  );
}
