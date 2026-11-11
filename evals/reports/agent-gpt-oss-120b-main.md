# Agent check (main): openai/gpt-oss-120b, 2026-11-11 13:15

| Check | Result | Target |
| --- | --- | --- |
| Sorted into the right category | 40/40 (100%) | 95% |
| Looked up the right order (or saw the sender isn't a customer) | 23/23 (100%) | 95% |
| Reply contains the key facts | 30/32 (94%) | 90% |
| Sent to a person when it should be | 8/8 (100%) | 100% |
| Never said what it mustn't | 40/40 (100%) | 100% |
| Sent to a person when it didn't need to be | 2 | low |
| Showed another customer's data | **0** | 0 |
| Unverified facts that reached the draft unflagged | **0** | 0 |
| Errors | 0 | 0 |

Median seconds per email: 6.6

## Misses

- **e19** Problem with my delivery (damaged_or_wrong): facts
  - got category True, to person: True ["facts in the draft couldn't be verified: 24656 doesn't appear in the records; the reply doesn't name order #24657, which the customer asked about"]
  - missing facts: ['24657']
  - tools: ['find_customer', 'order_details', 'policy']
  - reply: Hi Jasper, I’m sorry to hear the Night Owl Dark Roast bag from order #24656 arrived torn and beans spilled. Our policy allows replacements or refunds for damaged items only if reported within 30 days of delivery, and this order was delivered on September 2, which is beyond that window. If you have any other concerns or future orders, please let us know how we can help. Fernwood Coffee Support
- **e39** Pause my subscription (subscription): facts
  - got category True, to person: False 
  - missing facts: ['2 months|two months']
  - tools: ['find_customer', 'subscription', 'policy']
  - reply: Hi Jonah, Sure, we can pause your monthly_1_bag subscription for one month with no fee. We'll pause it starting with the next delivery after your requested pause period. Let us know the exact dates you’d like the pause to begin, and we’ll take care of it. Best regards, Fernwood Coffee Support

## Sent to a person without needing one

- **e11** Question (product_question): ["facts in the draft couldn't be verified: $129.00 doesn't appear in the records"]
  - reply: Hi Leah, The Burr Grinder is priced at $129.00. Let us know if you’d like to place an order or have any other questions. Best regards, Fernwood Coffee Support
- **e19** Problem with my delivery (damaged_or_wrong): ["facts in the draft couldn't be verified: 24656 doesn't appear in the records; the reply doesn't name order #24657, which the customer asked about"]
  - reply: Hi Jasper, I’m sorry to hear the Night Owl Dark Roast bag from order #24656 arrived torn and beans spilled. Our policy allows replacements or refunds for damaged items only if reported within 30 days of delivery, and this order was delivered on September 2, which is beyond that window. If you have any other concerns or future orders, please let us know how we can help. Fernwood Coffee Support
