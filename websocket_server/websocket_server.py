import asyncio
import websockets
import json
import logging
import socketserver
import threading
import queue
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TCPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        client_address = self.client_address[0]
        logger.info(f"TCP client connected from {client_address}")
        
        buffer = ""
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (separated by newlines)
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    message = message.strip()
                    
                    if message:
                        try:
                            json_data = json.loads(message)
                            data_queue.put(json_data)
                            logger.debug(f"Received data: simulation_time={json_data.get('simulation_time', 'N/A')}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON received: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            
        except ConnectionResetError:
            logger.info(f"TCP client {client_address} disconnected")
        except Exception as e:
            logger.error(f"TCP handler error: {e}")
        finally:
            logger.info(f"TCP client {client_address} connection closed")

class WebSocketServer:
    def __init__(self):
        self.clients = set()
        self.server = None
        self.running = False
        self.broadcast_task = None

    async def register(self, websocket):  # Fixed: removed 'path' parameter
        client_address = websocket.remote_address
        self.clients.add(websocket)
        logger.info(f"WebSocket client connected from {client_address[0]}:{client_address[1]} (total: {len(self.clients)})")
        
        try:
            # Send initial connection confirmation
            await websocket.send(json.dumps({
                "type": "connection_status",
                "status": "connected",
                "message": "Connected to drone data stream"
            }))
            
            # Keep connection alive
            await websocket.wait_closed()
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket client {client_address[0]}:{client_address[1]} disconnected normally")
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")
        finally:
            self.clients.discard(websocket)
            logger.info(f"WebSocket client {client_address[0]}:{client_address[1]} removed (remaining: {len(self.clients)})")

    async def broadcast_data(self):
        """Continuously broadcast data from queue to all connected clients"""
        logger.info("Starting data broadcast task")
        
        while self.running:
            try:
                # Check for new data
                if not data_queue.empty():
                    data = data_queue.get_nowait()
                    message = json.dumps(data)
                    
                    # Send to all connected clients
                    if self.clients:
                        disconnected_clients = set()
                        
                        for websocket in self.clients.copy():
                            try:
                                await websocket.send(message)
                            except websockets.exceptions.ConnectionClosed:
                                disconnected_clients.add(websocket)
                            except Exception as e:
                                logger.warning(f"Error sending to client: {e}")
                                disconnected_clients.add(websocket)
                        
                        # Remove disconnected clients
                        for websocket in disconnected_clients:
                            self.clients.discard(websocket)
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(1)
        
        logger.info("Data broadcast task stopped")

    async def start_websocket_server(self):
        """Start the WebSocket server"""
        self.running = True
        
        try:
            # Start WebSocket server
            self.server = await websockets.serve(
                self.register,
                "localhost",
                8765,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            logger.info("WebSocket server started on ws://localhost:8765")
            
            # Start broadcast task
            self.broadcast_task = asyncio.create_task(self.broadcast_data())
            
            # Keep server running
            await self.server.wait_closed()
            
        except Exception as e:
            logger.error(f"WebSocket server error: {e}")
        finally:
            self.running = False
            if self.broadcast_task:
                self.broadcast_task.cancel()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """TCP Server that handles each client in a separate thread"""
    allow_reuse_address = True
    daemon_threads = True

def run_websocket_server():
    """Run WebSocket server in separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    server = WebSocketServer()
    try:
        logger.info("Starting WebSocket server thread")
        loop.run_until_complete(server.start_websocket_server())
    except KeyboardInterrupt:
        logger.info("WebSocket server interrupted")
    finally:
        loop.close()

def main():
    global data_queue
    
    # Create shared data queue
    data_queue = queue.Queue(maxsize=1000)  # Limit queue size to prevent memory issues
    
    try:
        # Start TCP server
        logger.info("Starting TCP server on localhost:8766")
        tcp_server = ThreadedTCPServer(('localhost', 8766), TCPRequestHandler)
        tcp_thread = threading.Thread(target=tcp_server.serve_forever, daemon=True)
        tcp_thread.start()
        logger.info("TCP server started successfully")

        # Start WebSocket server
        logger.info("Starting WebSocket server")
        ws_thread = threading.Thread(target=run_websocket_server, daemon=True)
        ws_thread.start()
        
        # Keep main thread alive
        logger.info("All servers started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down servers...")
        tcp_server.shutdown()
        tcp_server.server_close()
        logger.info("Servers stopped")
    except Exception as e:
        logger.error(f"Server error: {e}")
        if 'tcp_server' in locals():
            tcp_server.shutdown()
            tcp_server.server_close()

if __name__ == "__main__":
    main()