# Public example corpus

These are synthetic, MIT-licensed review fixtures. `GOLD_CANDIDATE` means the expected state is defined; it does not mean a human panel, model family, Runtime, or third party has verified the case.

| Domain | Case | Direction | Status |
| --- | --- | --- | --- |
| coding | [Webhook deduplication across languages](coding/coding-cross-language/source.md) | `zh-Hans → fr` | GOLD_CANDIDATE |
| research | [Market research with a missing licensed paper](research/research-partial/source.md) | `en → zh-Hans` | GOLD_CANDIDATE |
| learning | [A learner changes from memorization to explanation practice](learning/learning-intent-change/source.md) | `fr → en` | GOLD_CANDIDATE |
| writing | [Bilingual article revision without publication authority](writing/writing-authority/source.md) | `zh-Hans → en` | GOLD_CANDIDATE |
| business | [Pricing decision with stale vendor terms](business/business-external-state/source.md) | `en → es` | GOLD_CANDIDATE |
| product-design | [Mobile onboarding redesign with parallel actions](product-design/product-design-parallel/source.md) | `ja → ko` | GOLD_CANDIDATE |
| general-chat | [A complex personal plan with explicit boundaries](general-chat/general-chat-mixed-constraints/source.md) | `ko → zh-Hans` | GOLD_CANDIDATE |

Every case contains `source.md`, `handoff.md`, `gold.json`, `expected-receipt.md`, and `expected-next-action.md`.
