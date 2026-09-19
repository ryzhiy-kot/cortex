---
type: reference
title: Orders table
description: Columns and semantics of the orders table.
tags:
  - tables
  - sql
---

The `orders` table records every customer purchase.

| Column | Type | Notes |
| ------ | ---- | ----- |
| `order_id` | integer | primary key |
| `customer_id` | integer | foreign key to [customers](/tables/customers.md) |
| `total_cents` | integer | order total, excluding tax |

Orders are typically read backwards in time for reporting. See the
[revenue guide](/guides/revenue.md).