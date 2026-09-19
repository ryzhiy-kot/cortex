---
type: guide
title: Revenue guide
description: How revenue is derived from orders.
tags:
  - guides
  - metrics
---

Revenue is the sum of approved `orders.total_cents` over a time window.

## Steps

1. Read [orders](/tables/orders.md).
2. Filter on `order_date`.
3. Sum `total_cents`.