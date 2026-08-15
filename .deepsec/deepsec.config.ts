import { defineConfig, type DeepsecPlugin } from "deepsec/config";
import { generatedMatchersPlugin } from "./generated-matchers.js";
import { mongodbMissingUserId } from "./matchers/mongodb-missing-user-id.js";

const trustOfficeMatchers: DeepsecPlugin = {
  name: "trustoffice-security-matchers",
  matchers: [mongodbMissingUserId],
};

export default defineConfig({
  defaultModel: "anthropic/claude-3.5-sonnet",
  defaultAgent: "pi",
  ai: {
    mode: "custom",
    provider: "openrouter",
    apiKeyEnv: "DEEPSEC_OPENROUTER_KEY",
    baseUrl: "https://openrouter.ai/api/v1",
    credentialHeader: { name: "Authorization", scheme: "bearer" },
  },
  projects: [
    { id: "TrustOfficeApp", root: ".." },
  ],
  plugins: [generatedMatchersPlugin, trustOfficeMatchers],
});
