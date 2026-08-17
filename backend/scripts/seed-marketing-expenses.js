// Seed marketing expenses — category-level summaries, NO line items
// Per Jeff: "I don't want each expense broken out. I want things categorized and summarized."

db.marketing_expenses.insertMany([
  {
    expense_id: "seed-marketing-build-001",
    category: "marketing_build",
    amount_cents: 1000000,
    period_month: null,
    description: "Marketing campaign build — content creation, ad creative, and ad management",
    source: "seed",
    expense_date: "2026-08-01T00:00:00.000Z",
    created_at: new Date().toISOString(),
    created_by: "kit-seed"
  },
  {
    expense_id: "seed-linkdaddy-001",
    category: "linkdaddy_seo",
    amount_cents: 151200,
    period_month: null,
    description: "LinkDaddy SEO — all-time backlink campaigns and press releases including prior work",
    source: "seed",
    expense_date: "2026-07-02T00:00:00.000Z",
    created_at: new Date().toISOString(),
    created_by: "kit-seed"
  },
  {
    expense_id: "seed-google-ads-001",
    category: "google_ads",
    amount_cents: 70000,
    period_month: null,
    description: "Google Ads — all-time search and display advertising spend",
    source: "seed",
    expense_date: "2026-08-01T00:00:00.000Z",
    created_at: new Date().toISOString(),
    created_by: "kit-seed"
  }
]);

// Create indexes
db.marketing_expenses.createIndex({ expense_id: 1 }, { unique: true });
db.marketing_expenses.createIndex({ category: 1 });
db.marketing_expenses.createIndex({ expense_date: 1 });

print("Seed complete. Documents inserted:");
printjson(db.marketing_expenses.countDocuments());
printjson(db.marketing_expenses.find({}, { _id: 0, expense_id: 1, category: 1, amount_cents: 1 }).toArray());