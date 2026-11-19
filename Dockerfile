FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 CRM_DB=/data/crm.db CHECKPOINT_DB=/data/checkpoints.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lead_agent ./lead_agent
COPY data ./data
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "lead_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
