# AgentCore Runtime requires linux/arm64. `agentcore launch` builds this for you
# via CodeBuild; to build locally use:  docker buildx build --platform linux/arm64 .
#
# Build context is the REPO ROOT:
#   docker build -f deploy/agentcore/Dockerfile -t resq-mesh-agentcore .
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt ./requirements.txt
COPY deploy/agentcore/requirements-agentcore.txt ./deploy/agentcore/requirements-agentcore.txt
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir bedrock-agentcore bedrock-agentcore-starter-toolkit

# Copy the application.
COPY app ./app
COPY examples ./examples
COPY deploy ./deploy

# AgentCore Runtime speaks HTTP on 8080.
EXPOSE 8080
CMD ["python", "deploy/agentcore/agent_entrypoint.py"]
