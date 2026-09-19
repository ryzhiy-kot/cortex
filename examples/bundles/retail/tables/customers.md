---
type: reference
title: Customers table
description: Columns and semantics of the customers table.
tags:
  - tables
  - sql
---

The `customers` table stores accounts for everyone who can place an order.

| Column | Type | Notes |
| ------ | ---- | ----- |
| `customer_id` | integer | primary key |
| `email` | text | unique login handle |

A customer may hold many [orders](/tables/orders.md).