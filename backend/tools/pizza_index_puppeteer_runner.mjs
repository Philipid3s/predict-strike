import puppeteerExtra from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';

puppeteerExtra.use(StealthPlugin());

function delay(milliseconds) {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

function parseInteger(value) {
  if (!value) {
    return null;
  }
  const normalized = String(value).replace(/[^0-9-]/g, '');
  if (!normalized) {
    return null;
  }
  const parsed = Number.parseInt(normalized, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function parseFloatValue(value) {
  if (!value) {
    return null;
  }
  const normalized = String(value).replace(/[^0-9.]/g, '');
  if (!normalized) {
    return null;
  }
  const parsed = Number.parseFloat(normalized);
  return Number.isNaN(parsed) ? null : parsed;
}

function flattenAccessibility(node, names = []) {
  if (!node) {
    return names;
  }
  if (node.name) {
    names.push({ role: node.role || '', name: node.name });
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      flattenAccessibility(child, names);
    }
  }
  return names;
}

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function buildSearchUrl(query) {
  return `https://www.google.com/maps/search/${encodeURIComponent(query)}`;
}

function scoreResult(result, payload) {
  const haystack = normalizeText(`${result.title} ${result.text}`);
  const displayName = normalizeText(payload.display_name);
  const locationCluster = normalizeText(payload.location_cluster || '');
  let score = 0;

  for (const token of displayName.split(' ')) {
    if (token && haystack.includes(token)) {
      score += 3;
    }
  }
  for (const token of locationCluster.split(' ')) {
    if (token && haystack.includes(token)) {
      score += 2;
    }
  }
  if (haystack.includes(displayName)) {
    score += 10;
  }
  if (haystack.includes('arlington')) {
    score += 2;
  }
  return score;
}

async function collectSearchResults(page) {
  const articleResults = await page.$$eval('article', (articles) =>
    articles.slice(0, 10).map((article) => {
      const link = article.querySelector('a[href*="/maps/place/"], a[href*="/maps/search/"]');
      return {
        title: link?.textContent?.trim() || '',
        text: article.textContent?.trim() || '',
        href: link?.href || null,
      };
    }),
  );

  if (articleResults.length) {
    return articleResults;
  }

  return await page.$$eval('a[href*="/maps/place/"], a[href*="/maps/search/"]', (links) =>
    links.slice(0, 20).map((link) => ({
      title: link.textContent?.trim() || '',
      text: link.closest('article')?.textContent?.trim() || link.parentElement?.textContent?.trim() || '',
      href: link.href || null,
    })),
  );
}

async function openBestResult(page, payload) {
  await page.goto(buildSearchUrl(payload.search_query || payload.display_name), {
    waitUntil: 'domcontentloaded',
    timeout: payload.timeoutMs,
  });
  await page.waitForSelector('a[href*="/maps/place/"], article, h1', { timeout: payload.timeoutMs });
  await delay(1500);

  const results = await collectSearchResults(page);
  if (!results.length) {
    return { resultUrl: page.url(), searchResults: [] };
  }

  const ranked = results
    .map((result, index) => ({ result, index, score: scoreResult(result, payload) }))
    .sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      return left.index - right.index;
    });

  const best = ranked[0]?.result || results[0];
  if (best?.href) {
    await page.goto(best.href, {
      waitUntil: 'domcontentloaded',
      timeout: payload.timeoutMs,
    });
    await page.waitForSelector('h1', { timeout: payload.timeoutMs });
    await delay(1800);
    return { resultUrl: best.href, searchResults: results };
  }

  return { resultUrl: page.url(), searchResults: results };
}

function parseAddress(names) {
  const match = names.find((entry) => entry.name.startsWith('Address:'));
  return match ? match.name.replace(/^Address:\s*/i, '').trim() : null;
}

function parseHours(names) {
  const match = names.find((entry) =>
    /(Open|Closed).*(See more hours|Open 24 hours|Opens)/i.test(entry.name),
  );
  return match ? match.name : null;
}

function parseRatingAndReviews(names) {
  let rating = null;
  let reviewsCount = null;
  for (const entry of names) {
    if (rating === null) {
      const ratingMatch = entry.name.match(/([0-5](?:\.[0-9])?)\s+stars/i);
      if (ratingMatch) {
        rating = parseFloatValue(ratingMatch[1]);
      }
    }
    if (reviewsCount === null) {
      const reviewMatch = entry.name.match(/([0-9,]+)\s+reviews/i);
      if (reviewMatch) {
        reviewsCount = parseInteger(reviewMatch[1]);
      }
    }
    if (rating !== null && reviewsCount !== null) {
      break;
    }
  }
  return { rating, reviewsCount };
}

function parsePopularTimes(names) {
  const dayEntry = names.find((entry) =>
    /^(Mondays|Tuesdays|Wednesdays|Thursdays|Fridays|Saturdays|Sundays)$/i.test(entry.name),
  );
  const hourly = names
    .map((entry) => {
      const match = entry.name.match(/(\d{1,3})%\s+busy\s+at\s+(\d{1,2})\s*(AM|PM)/i);
      if (!match) {
        return null;
      }
      return {
        percent: parseInteger(match[1]),
        hourLabel: `${match[2]} ${match[3].toUpperCase()}`,
        hour24: to24Hour(parseInteger(match[2]), match[3]),
        raw: entry.name,
      };
    })
    .filter(Boolean);

  return {
    dayLabel: dayEntry?.name || null,
    hourly,
  };
}

function to24Hour(hour, meridiem) {
  if (hour === null) {
    return null;
  }
  const upper = String(meridiem || '').toUpperCase();
  if (upper === 'AM') {
    return hour === 12 ? 0 : hour;
  }
  return hour === 12 ? 12 : hour + 12;
}

function localHourInEastern() {
  const parts = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    hour12: false,
    timeZone: 'America/New_York',
  }).formatToParts(new Date());
  const hourPart = parts.find((part) => part.type === 'hour');
  return hourPart ? Number.parseInt(hourPart.value, 10) : null;
}

function inferUsualBusyness(popularTimes) {
  if (!popularTimes.hourly.length) {
    return null;
  }
  const localHour = localHourInEastern();
  if (localHour === null) {
    return popularTimes.hourly[0].percent ?? null;
  }
  const exact = popularTimes.hourly.find((entry) => entry.hour24 === localHour);
  if (exact) {
    return exact.percent;
  }

  const sorted = [...popularTimes.hourly].sort(
    (left, right) => Math.abs((left.hour24 ?? 0) - localHour) - Math.abs((right.hour24 ?? 0) - localHour),
  );
  return sorted[0]?.percent ?? null;
}

function parseCurrentActivity(names) {
  const combined = names.map((entry) => entry.name).join('\n');
  const currentMatch = combined.match(
    /(currently|live[:\s]|right now[^\n]*?)(\d{1,3})%\s+busy|(\d{1,3})%\s+busy\s+now/i,
  );
  if (!currentMatch) {
    return {
      currentBusyness: null,
      currentLabel: null,
    };
  }
  const currentBusyness = parseInteger(currentMatch[2] || currentMatch[3]);
  const labelMatch = combined.match(
    /(busier than usual|less busy than usual|as busy as it gets|not too busy|usually not busy)/i,
  );
  return {
    currentBusyness,
    currentLabel: labelMatch ? labelMatch[1] : null,
  };
}

function inferClosedCurrentBusyness(isOpen) {
  if (isOpen === false) {
    return 0;
  }
  return null;
}

function parseOpenState(hoursLabel) {
  if (!hoursLabel) {
    return null;
  }
  if (/closed/i.test(hoursLabel)) {
    return false;
  }
  if (/open/i.test(hoursLabel)) {
    return true;
  }
  return null;
}

async function scrapePlace(payload) {
  const browser = await puppeteerExtra.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1400 });

    const { resultUrl, searchResults } = await openBestResult(page, payload);
    const accessibilityTree = await page.accessibility.snapshot({ interestingOnly: false });
    const names = flattenAccessibility(accessibilityTree, []);
    const hoursLabel = parseHours(names);
    const isOpen = parseOpenState(hoursLabel);
    const { rating, reviewsCount } = parseRatingAndReviews(names);
    const popularTimes = parsePopularTimes(names);
    const usualBusyness = inferUsualBusyness(popularTimes);
    const currentActivity = parseCurrentActivity(names);
    let currentBusyness = currentActivity.currentBusyness;
    let currentLabel = currentActivity.currentLabel;

    if (currentBusyness === null && isOpen === false) {
      currentBusyness = inferClosedCurrentBusyness(isOpen);
      currentLabel = 'closed';
    }

    const busynessDelta =
      currentBusyness !== null && usualBusyness !== null ? currentBusyness - usualBusyness : null;
    const headingText = await page
      .$eval('h1', (element) => element.textContent?.trim() || '')
      .catch(() => payload.display_name);

    return {
      display_name: headingText || payload.display_name,
      address: parseAddress(names),
      rating,
      reviews_count: reviewsCount,
      is_open: isOpen,
      current_busyness_percent: currentBusyness,
      usual_busyness_percent: usualBusyness,
      busyness_delta_percent: busynessDelta,
      current_busyness_label: currentLabel,
      capture_status:
        currentBusyness !== null || usualBusyness !== null || parseAddress(names) !== null
          ? 'puppeteer_detail_scrape_ok'
          : 'puppeteer_detail_scrape_partial',
      debug: {
        result_url: resultUrl,
        popular_times_day: popularTimes.dayLabel,
        popular_times_points: popularTimes.hourly.slice(0, 24),
        search_results: searchResults,
        accessibility_samples: names.slice(0, 200),
      },
    };
  } finally {
    await browser.close();
  }
}

async function main() {
  const payload = JSON.parse(process.argv[2] || '{}');
  if (!payload.display_name) {
    throw new Error('display_name is required');
  }
  const result = await scrapePlace(payload);
  process.stdout.write(JSON.stringify(result));
}

main().catch((error) => {
  process.stderr.write(
    JSON.stringify({
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exit(1);
});
