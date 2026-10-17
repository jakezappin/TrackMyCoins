/**
 * Buyer's premium. PCGS auction prices realized INCLUDE the buyer's premium (what the buyer paid).
 * To show the hammer price instead, divide out the house's premium. Houses use different rates by sale
 * type, so we try the usual rates and keep the one that gives a round hammer bid.
 */

const RATES: [RegExp, number[]][] = [
  [/stack/i, [0.22, 0.2, 0.18]],
  [/heritage/i, [0.2, 0.175]],
  [/greatcollections|great collections/i, [0.15, 0.1]],
  [/legend/i, [0.2, 0.175]],
  [/david lawrence|dla/i, [0.15, 0.1]],
  [/goldberg|kagin|bowers|teletrade|sotheby|christie/i, [0.2, 0.175, 0.15]],
];
const FALLBACK = [0.2, 0.22, 0.175, 0.15, 0.1];

export interface Hammer {
  hammer: number;
  rate: number;
  exact: boolean; // false when no rate gave a whole-dollar hammer (then the house's usual rate is used)
}

export function hammerPrice(price: number, auctioneer: string | null): Hammer {
  const rates = RATES.find(([re]) => re.test(auctioneer ?? ""))?.[1] ?? FALLBACK;
  let best: { r: number; h: number; score: number } | null = null;
  for (const r of rates) {
    const h = price / (1 + r);
    const whole = Math.abs(h - Math.round(h)) < 0.011;
    if (!whole) continue;
    const rounded = Math.round(h);
    // Bids above ~$100 move in $5/$10 steps, so rounder hammers are likelier.
    const score = (rounded % 10 === 0 ? 3 : rounded % 5 === 0 ? 2 : 1) - rates.indexOf(r) * 0.1;
    if (!best || score > best.score) best = { r, h: rounded, score };
  }
  if (best) return { hammer: best.h, rate: best.r, exact: true };
  const r = rates[0];
  return { hammer: Math.round((price / (1 + r)) * 100) / 100, rate: r, exact: false };
}
