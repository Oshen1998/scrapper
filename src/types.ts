// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * A single product row extracted from the DigiKey table.
 * Keys are the column header names (e.g. "Part Number", "Manufacturer").
 * We use an index signature because columns vary by category.
 */
export interface Product {
  [column: string]: string;
}

/**
 * Scraper configuration – change these values to control behaviour.
 */
export interface ScraperConfig {
  /** Starting URL (the DigiKey filter/category page) */
  url: string;
  /** Maximum number of table pages to scrape (set to Infinity to scrape all) */
  maxPages: number;
  /** Where to write products.json and products.csv */
  outputDir: string;
  /**
   * true  = run Chrome in the background (no GUI, faster, great for servers)
   * false = show the browser window (useful while developing)
   */
  headless: boolean;
  /** Milliseconds to wait between page navigations – reduces bot-detection risk */
  delayBetweenPages: number;
}

/** Summary printed at the end of each run */
export interface ScrapeResult {
  totalProducts: number;
  pagesScraped: number;
  columns: string[];
  outputFiles: string[];
}
