
# BESH

![BESH Logo Banner](images/BESH_LOGO_BANNER.png)


A high-performance batch processing API for large language models with support for both single-GPU and multi-GPU (8-GPU) deployments.

## Features

🚀 Intelligent Queue Management  
⚡ Advanced Parallel Processing  
🔄 Production-Ready Reliability  
📊 Real-Time Analytics Dashboard  
🎯 Enterprise-Scale Architecture  
💾 Persistent Storage  

## Quick Start

### Standard Deployment (Single GPU)

```bash
docker compose -f docker-compose.yml up -d --build --scale worker=4

# Access the dashboard
curl http://localhost:8080/
```

### High-Performance Deployment (24-GPU)

For high-throughput production workloads, use the 24-GPU configuration with load balancing:

```bash
export NGINX_CONF=nginx-24gpu.conf
export REMOTE_CLUSTER_HOST_A=<ip_remote_cluster>
export REMOTE_CLUSTER_HOST_B=<ip_remote_cluster>
docker compose -f docker-compose-multi-gpu.yml up -d --build --scale worker=12
```

## Screenshots

![BESH Dashboard Overview](images/Bashboard_overview.png)

Features:

- See throughput per 15min
- See uploads per 15min
- See stats per 24h
- See and delete individual batches

## Tips

Things you might want check:

- `MAX_WORKERS=128` & `MAX_CONCURRENT_BATCHES=10` in the docker compose files of the batch api.
  - if the batches are very large, maybe from concurrent batches, or visa versa.
  - Find your most efficient number of workers, I found 128 for H100 running a small model.
- `events {worker_connections 2048;}` Make sure this value is larger then MAX_WORKERS.
- Consider uploading the model once for faster init on 8 gpus.
- There is no storage managment system -> make sure you delete your batch files (in & out)


## 8-GPU Architecture Overview

The 8-GPU deployment provides horizontal scaling with the following architecture:

```mermaid
graph TB
    subgraph "Client Layer"
        Client[Client Applications]
    end
    
    subgraph "Load Balancer Layer"
        LB[Nginx Load Balancer<br/>:8000]
    end
    
    subgraph "vLLM Inference Layer"
        GPU0[vLLM GPU-0<br/>:8001]
        GPU1[vLLM GPU-1<br/>:8002]
        GPU2[vLLM GPU-2<br/>:8003]
        GPU3[vLLM GPU-3<br/>:8004]
        GPU4[vLLM GPU-4<br/>:8005]
        GPU5[vLLM GPU-5<br/>:8006]
        GPU6[vLLM GPU-6<br/>:8007]
        GPU7[vLLM GPU-7<br/>:8008]
    end
    
    subgraph "API Layer"
        BatchAPI[Batch API<br/>:8080]
    end
    
    subgraph "Storage Layer"
        DB[(Database)]
        Models[(Model Cache)]
        Files[(Batch Files)]
    end
    
    Client --> LB
    LB --> GPU0
    LB --> GPU1
    LB --> GPU2
    LB --> GPU3
    LB --> GPU4
    LB --> GPU5
    LB --> GPU6
    LB --> GPU7
    
    BatchAPI --> LB
    BatchAPI --> DB
    BatchAPI --> Files
    
    GPU0 --> Models
    GPU1 --> Models
    GPU2 --> Models
    GPU3 --> Models
    GPU4 --> Models
    GPU5 --> Models
    GPU6 --> Models
    GPU7 --> Models
    
    classDef gpu fill:#e1f5fe
    classDef lb fill:#f3e5f5
    classDef api fill:#e8f5e8
    classDef storage fill:#fff3e0
    
    class GPU0,GPU1,GPU2,GPU3,GPU4,GPU5,GPU6,GPU7 gpu
    class LB lb
    class BatchAPI api
    class DB,Models,Files storage
```

## Options

### Test Model Inference

```bash
# Test vLLM endpoint directly
curl http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "<your_model_name>",           
        "prompt": "Why is open source important for the progress of AI?",
        "max_tokens": 100,
        "temperature": 0.3
    }'

# Test batch API health
curl http://localhost:8080/health
```

### Pytest

Run individual endpoint tests + 100 calls to openai gpt-nano. We do not have a pytest for GPUs. We advise running the `test_large.py` and `test_api.py` manually to check GPU deployment. Since vLLM is openai compatible, we did not see the need for those test.

```bash
# MAKE SURE YOU HAVE TEST_API_KEY set in .env
docker-compose -f docker-compose.test.yml up --build --scale worker=2
```

### Helper files

- [`scripts/check_batch.py`](scripts/check_batch.py) – CLI check batch from ID
- [`scripts/delete_x.py`](scripts/delete_x.py) – CLI delete files and/or Bacthes

### CI/CD

Recommended to only update the batch-api using this command for CI/CD pipelines.

```bash
docker compose -f <compose-file> up -d --no-deps --build batch-api
```

## Contribute

Contributions are welcome! Feel free to open an issue or submit a pull request.


## Contact

- **Author:** Floris Fok
- **📧 Email:** [floris.fok@prosus.com](mailto:floris.fok@prosus.com)
- **🔗 LinkedIn:** [floris-jan-fok](https://www.linkedin.com/in/floris-jan-fok/)