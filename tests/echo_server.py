# Copyright 2025 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/usr/bin/env python3
"""Minimal MCP server for testing — exposes echo and add tools."""
import json
import sys


def handle_initialize(req):
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "test-echo-server", "version": "0.1.0"},
    }


def handle_tools_list(req):
    return {
        "tools": [
            {
                "name": "echo",
                "description": "Echo back the input message",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to echo"}
                    },
                    "required": ["message"],
                },
            },
            {
                "name": "add",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
            },
            {
                "name": "delete_item",
                "description": "Delete an item (dangerous)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Item ID to delete"}
                    },
                    "required": ["id"],
                },
            },
        ]
    }


def handle_tools_call(req):
    name = req["params"]["name"]
    args = req["params"]["arguments"]

    if name == "echo":
        return {
            "content": [{"type": "text", "text": json.dumps({"echo": args.get("message", "")})}]
        }
    elif name == "add":
        return {
            "content": [{"type": "text", "text": json.dumps({"sum": args["a"] + args["b"]})}]
        }
    elif name == "delete_item":
        return {
            "content": [{"type": "text", "text": json.dumps({"deleted": args["id"]})}]
        }
    return {"content": [{"type": "text", "text": json.dumps({"error": "unknown tool"})}]}


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        handler = HANDLERS.get(method)

        if method == "notifications/initialized":
            continue  # notification, no response

        if handler:
            result = handler(req)
            response = {"jsonrpc": "2.0", "id": req.get("id", 0), "result": result}
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req.get("id", 0),
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
