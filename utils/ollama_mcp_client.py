from fastmcp import Client
from fastmcp.exceptions import ToolError
from ollama import Client as ollama_client
from openai import OpenAI
import asyncio
from contextlib import AsyncExitStack
from ollama._types import ChatRequest
import re
import json

class MCPClient:
    def __init__(self,
                 mcp_servers={"playwright":{"url":"http://127.0.0.1:8082/sse"}}, # standard mcp server dictionary
                 ollama_model="qwen3:latest", # model name as listed in your ollama
                 openai_model=None,
                 ollama_url="http://127.0.0.1:11434", # point to your ollama server
                 ollama_timeout=300,
                 prompt= "You are an assistant with access to playwright tools, " \
                         "they can help you access web information or search for real-time data. "\
                         "You may use the browser to navigate to a search engine to help. "\
                         "Use your tools as needed to answer the user's queries and always " \
                         "include only your final answer within <answer>...</answer> tags",
                 timeout=30, # number of llm responses without receiving an answer
                 debug=False, # print out each message
                 max_tokens=10000 
                ):
        # Initialize session and client objects
        self.session = None
        self.tools = []
        self.exit_stack = AsyncExitStack()
        self.openai_model = openai_model
        self.ollama = ollama_client(ollama_url,timeout=ollama_timeout)
        self.ollama_model = ollama_model
        if openai_model:
            self.openai = OpenAI(max_retries=20)           
        self.mcp_servers = mcp_servers
        self.prompt = prompt
        self.timeout = timeout
        self.debug = debug
        self.max_tokens = max_tokens

    async def connect_to_servers(self):
        # Standard MCP configuration with multiple servers
        config = {
            "mcpServers": self.mcp_servers
        }

        # Create a client that connects to all servers
        self.session = Client(config)

        # List available tools from the MCP server
        async with self.session:
            self.tools = await self.session.list_tools()
        if self.debug:
            print("\nConnected to server with tools:", [tool.name for tool in self.tools])
            
    async def openai_process_query(self, query: str) -> str:
        """Process a query using openai and available tools"""
        input_messages = [
            {
                "role": "developer",
                "content": self.prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]
    
        available_tools = [{
            "type":"function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        } for tool in self.tools]
        num_responses = 0
        answer = []
        requests = []
        responses = []
        tool_count = 0
        async with self.session:
            while num_responses < self.timeout and not answer:
                response = self.openai.responses.create(
                    model=self.openai_model,
                    input=input_messages,
                    tools=available_tools,
                    max_output_tokens=self.max_tokens,
                    truncation='auto'
                )
                num_responses += 1
                for tool_call in response.output:
                    if tool_call.type != "function_call":
                        text = " ".join([m.text for m in tool_call.content])
                        answer = re.findall("<answer>(.*?)</answer>", text, re.DOTALL)
                        continue
                
                    name = tool_call.name
                    args = json.loads(tool_call.arguments)
                
                    result = await self.session.call_tool(name,args)
                    tool_count += 1
                    input_messages.append(tool_call)
                    input_messages.append({
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": str(result)
                    })
        if self.debug:
            print(input_messages)
        input_messages = [m.model_dump_json() if type(m) != dict else m for m in input_messages]
        return answer, input_messages, tool_count
        
    async def ollama_process_query(self, query: str) -> str:
        """Process a query using Ollama and available tools"""
        messages = [
            {
                "role": "system",
                "content": self.prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]
    
        available_tools = [{
            "type":"function",
            "function":{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
            }
        } for tool in self.tools]
        num_responses = 0
        answer = []
        requests = []
        responses = []
        tool_count = 0
        async with self.session:
            while num_responses < self.timeout and not answer:
                response = self.ollama.chat(
                    model=self.ollama_model, # Specify the Ollama model
                    messages=messages,
                    tools=available_tools,
                    options={"num_ctx":self.max_tokens}
                )
                num_responses += 1
            
                # Process response and handle tool calls
                final_text = []
        
                assistant_message_content = ""
                if self.debug:
                    print(response)
                message = response.message
                text = message.get('content','')
                tool_calls = message.get('tool_calls',[])
                assistant_message_content = text
                final_text.append(text)
                answer = re.findall("<answer>(.*?)</answer>", text, re.DOTALL)
                messages.append(json.loads(response.message.model_dump_json()))
                if tool_calls:
                    for tool in tool_calls:
                        tool_count += 1
                        try:
                            result = await self.session.call_tool(tool.function.name,tool.function.arguments)
                            result = result.content[0].text
                        except ToolError as e:
                            result = e.args[0]
                        final_text.append(f"[Calling tool {tool.function.name} with args {tool.function.arguments}]")
                        messages.append({
                            "role": "tool",
                            "type": "tool_result",
                            "content": result
                        })
        if self.debug:
            print(messages)
        return answer, messages, tool_count
    
    async def chat_loop(self):
        """Run an interactive chat loop."""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                # Process the query, which will now stream the LLM response to console.
                if self.openai_model:
                    resp = await self.openai_process_query(query)
                else:
                    resp = await self.ollama_process_query(query)
                print(resp)
                # The response is already printed during streaming in process_query.

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()

