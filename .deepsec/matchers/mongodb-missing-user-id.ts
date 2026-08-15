import { regexMatcher, type MatcherPlugin } from "deepsec/config";

// Catches the #1 vulnerability class in TrustOffice: MongoDB find/update/delete
// operations that are missing user_id in the filter dict.
export const mongodbMissingUserId: MatcherPlugin = {
  slug: "mongodb-missing-user-id",
  description:
    "MongoDB query (find_one/find/update_one/delete_one/delete_many/replace_one) missing user_id filter — IDOR risk",
  noiseTier: "normal",
  filePatterns: ["backend/routers/**/*.py"],
  examples: [
    'db.trusts.find_one({"trust_id": trust_id})',
    'db.minutes.update_one({"minutes_id": mid}, {"$set": {...}})',
    'db.documents.delete_one({"doc_id": did})',
    'db.users.find_one({"email": email})',
  ],
  match(content, filePath) {
    return regexMatcher(
      "mongodb-missing-user-id",
      [
        // Method calls with filter dicts that likely lack user_id
        {
          regex: /\.(find_one|find|update_one|delete_one|delete_many|replace_one)\s*\(\s*\{(?!.*user_id)[^}]*\}\s*\)/g,
          label: "MongoDB query likely missing user_id in filter",
        },
      ],
      content,
    );
  },
};