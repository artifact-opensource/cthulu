# Cthulu Web UI

The autonomous trading interface for the Cthulu system. Built with Angular, tailored for high-performance monitoring.

## Prerequisites

- Node.js (v18 or higher)
- NPM

## Installation

1. Navigate to the UI directory:
   ```powershell
   cd C:\workspace\cthulu\ui
   ```

2. Install dependencies:
   ```powershell
   npm install --legacy-peer-deps
   ```

## Development

Start the local development server:
```powershell
npm run dev
```
Access the UI at **http://localhost:4200**.

## Production Build

Build the project for production (optimization enabled):
```powershell
npm run build
```
Output files will be generated in the `dist/` folder.

## Deployment (Vercel)

This project is configured for Vercel deployment.

1. **Install Vercel CLI** (if not already installed):
   ```powershell
   npm install -g vercel
   ```

2. **Deploy**:
   ```powershell
   vercel
   ```
   Follow the interactive prompts.

3. **Production Deployment**:
   ```powershell
   vercel --prod
   ```

## Important Note on Connectivity

This UI connects to a **local backend** (`http://localhost:5000`) to fetch live trading data. 
- When running on Vercel, the site will look for `localhost:5000` on the **visitor's machine**. 
- If the backend is off, the UI will show an "Offline" state but remain accessible as a static website.
