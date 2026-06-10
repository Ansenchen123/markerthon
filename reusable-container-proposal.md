# Reusable Container Proposal Summary

## Problem

Single-use takeout containers create avoidable waste and make recovery rates hard to measure. A reusable container program needs a simple operating loop that merchants can run at checkout and returns, while public-sector observers need aggregate metrics without direct control over merchant workflows.

## Product Concept

Markerthon models a reusable cup and meal-box flow:

1. A merchant issues containers for an invoice.
2. The backend creates a QR value for the store, invoice, and category.
3. A return scan records one returned container.
4. Daily CSV rows preserve sold and recovered events.
5. Government dashboard APIs aggregate current monthly usage and recovery metrics.

## Roles

- Merchant: registers or logs in, creates QR batches, scans returns, and views store-level sold and recovered statistics.
- Government user: logs in separately and views aggregate dashboard data.
- Backend: owns authentication, authorization boundaries, database state, QR hashing, daily CSV rows, and dashboard aggregation.

## Container Categories

The current demo supports two category labels:

- `cup`
- `meal_box`

Each store, invoice, and category combination has one QR value. Repeating the same combination increases the loan counts instead of creating a second QR value.

## Data Model Notes

- `loans.item_count` is cumulative issued count.
- `loans.returned_count` is cumulative returned count.
- `loans.remaining_count` is current unreturned count.
- `loans.qr_token_hash` stores a SHA-256 hash of the QR value.
- The plain QR value is returned by the API and written to local daily CSV rows, but it is not stored in the `loans` table.

## Dashboard Metrics

The government dashboard focuses on:

- Monthly issued count.
- Monthly returned count.
- Remaining count.
- Recovery rate.
- Enterprise count.
- Regional distribution.
- Top stores by issued count.
- Store-level detail for a selected month.

## Demo Scope

This repository is a local demonstration. Before any hosted deployment, the owner should rotate runtime secrets, configure production CORS and HTTPS, replace demo credentials, and decide whether daily CSV files should remain local-only or be moved to managed storage.
