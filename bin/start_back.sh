#!/bin/bash


cd backend
source .venv/bin/activate
DATABASE_URL="postgresql+psycopg://localhost/cloud_pricing_dev" uvicorn src.main:app --reload --port 8000 > "../backend_$$.log" 2>&1 
