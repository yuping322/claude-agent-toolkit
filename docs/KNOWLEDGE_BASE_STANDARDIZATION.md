# 知识库标准化方案

## 概述

本文档描述了如何在 Claude Agent Toolkit 中标准化外部依赖，特别是知识库。通过 MCP (Model Context Protocol) 协议，我们可以统一不同类型的知识库接口，让 Agent 能够以一致的方式访问各种知识源。

## 核心设计原则

### 1. 抽象接口标准化
- `KnowledgeBaseInterface`: 定义了知识库的核心操作接口
- `KnowledgeItem`: 标准化的知识项数据结构
- `SearchQuery`: 统一的搜索查询格式

### 2. MCP协议适配
- 通过 `StdioMCPTool` 和 `HttpMCPTool` 包装外部知识库服务
- 跨进程通信，无需修改 Agent 核心代码
- 支持热插拔和动态配置

### 3. 依赖注入机制
- `KnowledgeBaseRegistry`: 后端实现注册中心
- `KnowledgeBaseTool.create()`: 工厂方法创建工具实例
- 支持运行时切换不同的知识库实现

## 架构图

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│      Agent      │────│ KnowledgeBaseTool │────│ MCP Protocol   │
│                 │    │                  │    │                 │
│ - search()      │    │ - search()       │    │ - Stdio/HTTP    │
│ - store()       │    │ - store()        │    │ - Cross-process │
│ - retrieve()    │    │ - retrieve()     │    │ - Tool calling  │
│ - delete()      │    │ - delete()       │    └─────────────────┘
└─────────────────┘    └──────────────────┘             │
                         │                            │
                         ▼                            ▼
                ┌──────────────────┐    ┌──────────────────┐
                │   Backend Impl   │    │  External MCP   │
                │                  │    │   Server        │
                │ - Vector DB      │    │                 │
                │ - File System    │    │ - Vector DB     │
                │ - In Memory      │    │ - API Service   │
                │ - External API   │    │ - Custom Logic  │
                └──────────────────┘    └──────────────────┘
```

## 使用方法

### 1. 直接实现 KnowledgeBaseInterface

```python
from claude_agent_toolkit.tool.knowledge_base import KnowledgeBaseTool, InMemoryKnowledgeBase

# 创建内存知识库工具
kb_tool = KnowledgeBaseTool.create(
    backend=InMemoryKnowledgeBase(),
    name="company_docs"
)

# 使用 Agent
agent = Agent(tools=[kb_tool])
result = await agent.run("搜索公司文档中关于API的信息")
```

### 2. 使用 MCP 包装外部服务

```python
from claude_agent_toolkit.tool.mcp import StdioMCPTool
from claude_agent_toolkit.tool.knowledge_base import KnowledgeBaseTool, MCPKnowledgeBaseAdapter

# 配置外部 MCP 知识库服务
external_kb_mcp = StdioMCPTool(
    command="node",
    args=["path/to/knowledge_base_server.js"],
    name="external_kb"
)

# 创建适配器
kb_adapter = MCPKnowledgeBaseAdapter(external_kb_mcp)

# 创建工具
kb_tool = KnowledgeBaseTool.create(
    backend=kb_adapter,
    name="external_kb"
)

# 使用 Agent
agent = Agent(tools=[kb_tool])
```

### 3. 注册和工厂模式

```python
from claude_agent_toolkit.tool.knowledge_base import KnowledgeBaseRegistry

# 注册不同的后端实现
KnowledgeBaseRegistry.register("vector_db", VectorKnowledgeBase)
KnowledgeBaseRegistry.register("filesystem", FileSystemKnowledgeBase)

# 通过配置创建
def create_kb_from_config(config: dict):
    backend = KnowledgeBaseRegistry.create_backend(
        config["type"],
        **config.get("params", {})
    )
    return KnowledgeBaseTool.create(backend=backend, name=config["name"])
```

## 支持的知识库类型

### 1. 内置实现
- **InMemoryKnowledgeBase**: 内存存储，适合测试和小规模使用
- **FileSystemKnowledgeBase**: 文件系统存储，支持持久化

### 2. 外部集成
- **向量数据库**: Pinecone, Weaviate, Qdrant 等
- **文档存储**: Elasticsearch, MongoDB 等
- **API服务**: 任何提供 REST/gRPC 接口的知识库服务
- **自定义实现**: 通过实现 KnowledgeBaseInterface

## MCP 服务器示例

### Stdio MCP 服务器 (Node.js)

```javascript
// knowledge_base_server.js
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

class KnowledgeBaseServer {
  constructor() {
    this.server = new Server(
      {
        name: 'knowledge-base',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
  }

  setupToolHandlers() {
    this.server.setRequestHandler('tools/call', async (request) => {
      const { name, arguments: args } = request.params;

      switch (name) {
        case 'search_knowledge':
          return await this.handleSearch(args);
        case 'store_knowledge':
          return await this.handleStore(args);
        // ... 其他操作
      }
    });
  }

  async handleSearch(args) {
    // 实现搜索逻辑
    const results = await this.searchBackend(args.query, args.limit);
    return {
      content: [{ type: 'text', text: JSON.stringify(results) }]
    };
  }

  async handleStore(args) {
    // 实现存储逻辑
    const result = await this.storeBackend(args.items);
    return {
      content: [{ type: 'text', text: JSON.stringify(result) }]
    };
  }
}

// 启动服务器
const server = new KnowledgeBaseServer();
const transport = new StdioServerTransport();
await server.server.connect(transport);
```

### HTTP MCP 服务器

```python
# knowledge_base_http_server.py
from fastmcp import FastMCP
from typing import List, Dict, Any

app = FastMCP("Knowledge Base Server")

class KnowledgeBaseManager:
    def __init__(self):
        self.items = {}

    @app.tool()
    async def search_knowledge(
        self,
        query: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """搜索知识库"""
        results = []
        for item_id, item in self.items.items():
            if query.lower() in item['content'].lower():
                results.append({
                    'id': item_id,
                    'content': item['content'],
                    'score': 0.8  # 简化评分
                })

        return {
            'results': results[:limit],
            'total': len(results)
        }

    @app.tool()
    async def store_knowledge(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """存储知识项"""
        stored_ids = []
        for item in items:
            item_id = f"kb_{len(self.items)}"
            self.items[item_id] = item
            stored_ids.append(item_id)

        return {'stored_ids': stored_ids}

# 运行服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 配置示例

### YAML 配置

```yaml
knowledge_bases:
  - name: company_docs
    type: vector_db
    params:
      connection_string: "postgresql://localhost:5432/knowledge"
      collection: "company_documents"

  - name: api_reference
    type: filesystem
    params:
      storage_path: "./api_docs"

  - name: external_kb
    type: mcp_stdio
    params:
      command: "node"
      args: ["external_kb_server.js"]
```

### 环境变量配置

```bash
# 知识库配置
KB_COMPANY_DOCS_TYPE=vector_db
KB_COMPANY_DOCS_CONNECTION_STRING=postgresql://...

KB_API_REFERENCE_TYPE=filesystem
KB_API_REFERENCE_STORAGE_PATH=./api_docs

KB_EXTERNAL_TYPE=mcp_stdio
KB_EXTERNAL_COMMAND=node
KB_EXTERNAL_ARGS=external_kb_server.js
```

## 优势

### 1. 标准化接口
- Agent 无需了解具体实现细节
- 统一的搜索、存储、检索接口
- 易于测试和维护

### 2. 灵活的扩展性
- 支持多种后端实现
- 运行时切换知识库
- 插件化架构

### 3. MCP 协议优势
- 跨进程通信，安全性高
- 支持多种传输协议 (Stdio, HTTP, SSE)
- 标准化工具调用协议

### 4. 依赖注入
- 构造函数注入
- 工厂模式创建
- 注册中心管理

## 最佳实践

### 1. 错误处理
```python
try:
    results = await kb_tool.search_knowledge("query")
    if not results["success"]:
        logger.error(f"Search failed: {results['error']}")
except Exception as e:
    logger.error(f"Knowledge base error: {e}")
```

### 2. 连接池管理
```python
# 为高并发场景使用连接池
kb_tool = KnowledgeBaseTool.create(
    backend=VectorKnowledgeBase(connection_pool=pool),
    workers=4  # 多进程处理
)
```

### 3. 缓存策略
```python
# 添加缓存层
cached_kb = CachedKnowledgeBase(
    backend=actual_backend,
    cache_ttl=3600
)
kb_tool = KnowledgeBaseTool.create(backend=cached_kb)
```

## 总结

通过 MCP 协议和抽象接口设计，我们成功实现了知识库依赖的标准化：

1. **统一接口**: `KnowledgeBaseInterface` 定义了标准操作
2. **协议适配**: MCP 允许跨进程集成外部服务
3. **依赖注入**: 支持灵活的配置和切换
4. **扩展性**: 易于添加新的知识库实现

这种设计让 Agent 能够无缝集成各种知识源，同时保持代码的简洁和可维护性。</content>
<parameter name="filePath">/Users/fengzhi/Downloads/git/claude_code_sdk/claude-agent-toolkit/docs/KNOWLEDGE_BASE_STANDARDIZATION.md