#!/bin/bash
echo "Installing Playwright browsers..."
playwright install
echo "Playwright install completed."

# Se estiver em um ambiente Linux (como o Streamlit Cloud)
echo "Installing system dependencies..."
playwright install-deps
echo "Dependencies installed."