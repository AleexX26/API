# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML, CSS and plain JavaScript served by FastAPI (`web/`); no framework. Strict CSP: no inline styles or scripts, `style-src 'self'`.

## Users

Administration staff of La Imprenta de Internet (a print shop). They read a customer's email (the owner reads WhatsApp), need to know quickly which supplier prints the job cheapest and how much margin the shop's own price leaves. Desktop first (confirmed); not technical; they use it many times a day.

## Product Purpose

Local price comparator of print suppliers (Print24, Onlineprinters, Printai, TusKamisetas) plus the shop's own prices. Success: an administrator opens it, enters or pastes the customer's order and within seconds knows the cheapest supplier and the shop's difference against each supplier. Focus now: business cards at 100%, then other products.

## Positioning

It compares like with like (same size, paper weight, sides, finish) and shows the shop's own web price beside the suppliers, with the margin against each.

## Open decisions

- Visual world: free to change (the user allowed changing all colors and everything). First thing to show: who is cheapest (confirmed).
