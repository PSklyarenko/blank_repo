FROM python:3.13-slim

WORKDIR /app

ENV PORT=3000
ENV DATABASE_PATH=/db/local.db

COPY app.py ./

RUN mkdir -p /db

EXPOSE 3000

CMD ["python", "app.py"]
