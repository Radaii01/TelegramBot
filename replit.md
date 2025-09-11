# Overview

This is a Telegram bot application for managing an e-cigarette/vaping product sales system. The bot facilitates inventory management, sales tracking, and customer interaction for VapSolo and Elf Bar products. It includes role-based access control with admin and seller (árusító) permissions, supports promotional campaigns, VIP offers, and provides detailed product information to customers.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Python Telegram Bot Library**: Uses the `python-telegram-bot` library for handling Telegram API interactions
- **Async/Await Pattern**: Implements asynchronous programming for handling multiple concurrent user interactions
- **Event-Driven Architecture**: Uses command handlers, callback query handlers, and message handlers for different types of user interactions

## Authentication & Authorization
- **Role-Based Access Control**: Three-tier permission system:
  - Admin (single user ID: 5437277473)
  - Sellers/Árusítók (predefined user ID list)
  - Regular customers (default access level)
- **Session Management**: User sessions stored in memory using `user_sessions` dictionary

## Data Storage
- **In-Memory Storage**: All data stored in Python dictionaries and variables:
  - `keszlet`: Product inventory organized by brand (VapSolo, Elf Bar)
  - `akciok`: Current promotional campaigns
  - `vip`: VIP customer offers
  - `sales_counters`: Sales tracking per seller
  - `user_sessions`: User interaction state management

## Product Management
- **Two Main Product Categories**: VapSolo and Elf Bar e-cigarettes
- **Product Information System**: Detailed specifications stored in `termek_leirasok` dictionary
- **Dynamic Inventory**: Real-time inventory management through bot commands

## User Interface
- **Inline Keyboard Navigation**: Uses Telegram's inline keyboards for menu-driven interactions
- **Multi-Language Support**: Interface appears to be in Hungarian
- **Interactive Menus**: Hierarchical menu system for browsing products and categories

## Configuration Management
- **Environment Variables**: Bot token stored as environment variable for security
- **Hardcoded Configuration**: User IDs and basic settings defined as constants in code
- **Error Handling**: Graceful fallback for import errors and missing environment variables

# External Dependencies

## Telegram Bot API
- **python-telegram-bot**: Main library for Telegram bot functionality
- **Telegram Platform**: All user interactions happen through Telegram messenger

## Runtime Environment
- **Python Environment Variables**: Requires `BOT_TOKEN` environment variable
- **Replit Hosting**: Designed to run on Replit platform (based on file structure)

## Third-Party Services
- **Telegram Servers**: All message delivery and user interaction through Telegram's infrastructure
- **No External Databases**: Currently uses in-memory storage only
- **No Payment Processing**: No integrated payment systems detected

## System Requirements
- **Python 3.7+**: Required for async/await functionality
- **Internet Connection**: Required for Telegram API communication
- **Persistent Runtime**: Needs continuous execution to maintain session data