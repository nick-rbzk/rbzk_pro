import json
import logging
import time
import os

from typing import List, Optional

from coinbase.websocket import WSClient, WebsocketResponse

from cb_trades.tasks import redis_store_price

logger = logging.getLogger(__name__)


class CoinbaseWebSocketHandler:
    """
    Handles Coinbase WebSocket connection using the official CDP SDK.
    
    The SDK automatically handles:
    - Permessage-deflate compression
    - Authentication with API keys
    - Heartbeat management
    """
    
    def __init__(
        self,
        product_ids: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ):
        """
        Initialize the WebSocket handler.
        
        Args:
            api_key: Your Coinbase CDP API key (format: "organizations/{org_id}/apiKeys/{key_id}")
            api_secret: Your Coinbase CDP API secret (PEM format)
            product_ids: List of product IDs to watch (e.g., ["BTC-USD", "ETH-USD"])
            task_id: Optional Celery task ID for management
        """
        self.api_key = os.environ.get("COINBASE_KEY_NAME")
        self.api_secret = os.environ.get("COINBASE_KEY_SECRET")
        self.product_ids = product_ids
        self.task_id = task_id
        self.ws_client = None
        self.running = False
        self.error_count = 0
        self.max_errors = 10  # Maximum consecutive errors before giving up
        self.reconnect_count = 0
        self.max_reconnects = 20  # Maximum reconnection attempts
        self.reconnect_delay = 1  # Delay between reconnection attempts in seconds
        
    def on_message(self, msg: str) -> None:
        """
        Callback for incoming WebSocket messages.
        
        Uses the built-in WebsocketResponse parser for cleaner data access.
        """
        try:
            # Parse message using SDK's built-in response parser
            message = json.loads(msg)
            print(message)
            # ws_object = WebsocketResponse(json.loads(msg))
            ws_object = message 
            # Handle ticker channel messages
            if ws_object:
                pass
                # for event in ws_object.events:
                #     if hasattr(event, 'tickers'):
                #         for ticker in event.tickers:
                #             # Create a structured message for Celery
                #             price_data = {
                #                 'channel': 'ticker',
                #                 'product_id': ticker.product_id,
                #                 'price': ticker.price,
                #                 'volume_24h': ticker.volume_24_h,
                #                 'best_bid': ticker.best_bid,
                #                 'best_ask': ticker.best_ask,
                #                 'side': ticker.side,
                #                 'trade_id': ticker.trade_id,
                #                 'time': ticker.time
                #             }
                #             print(event)
                #             # Send to Celery for processing
                #             # redis_store_price.delay(json.dumps(price_data))
                #             # logger.debug(f"Price update: {ticker.product_id} = ${ticker.price}")
                            
                #             # Reset error counter on successful message
                #             self.error_count = 0
            
            # Handle heartbeat channel (keep connection alive automatically)
            elif ws_object.channel == "heartbeats":
                logger.debug("Heartbeat received")
                # Reset error counter on successful heartbeat
                self.error_count = 0
                
            # Handle subscriptions channel (confirmation of subscription)
            elif ws_object.channel == "subscriptions":
                logger.info(f"Successfully subscribed to: {ws_object.events}")
                
            # Handle any other channels
            else:
                logger.debug(f"Received message from channel: {ws_object.channel}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            self.error_count += 1
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self.error_count += 1
    
    def on_open(self) -> None:
        """Callback when WebSocket connection is established."""
        logger.info(f"WebSocket connection opened for {self.product_ids}")
        self.error_count = 0  # Reset error counter on successful connection
        self.reconnect_count = 0  # Reset reconnect counter on successful connection
    
    def on_close(self) -> None:
        """Callback when WebSocket connection is closed."""
        logger.info("WebSocket connection closed")
    
    def start(self) -> None:
        """
        Start the WebSocket connection with automatic reconnection on errors.
        
        Implements the reconnection loop:
        - Starts the WebSocket client
        - Checks for errors in a loop
        - Closes and restarts the client if an error occurs
        - Continues until stopped or max reconnects exceeded
        """
        logger.info(f"Starting WebSocket connection for {self.product_ids}")
        self.running = True
        
        # Main connection loop
        while self.running and self.reconnect_count < self.max_reconnects:
            try:
                # Initialize the WebSocket client if needed
                if not self.ws_client:
                    self.ws_client = WSClient(
                        api_key=self.api_key,
                        api_secret=self.api_secret,
                        on_message=self.on_message,
                        on_open=self.on_open,
                        on_close=self.on_close,
                        # on_error=self.on_error,  # Error callback
                        verbose=True  # Set to True for debug logging
                    )
                
                # Start the client connection
                logger.info(f"Attempting to connect (attempt {self.reconnect_count + 1})...")
                self.ws_client.open()
                
                # Subscribe to channels
                self.ws_client.subscribe(
                    product_ids=self.product_ids,
                    channels=["ticker", "heartbeats"]
                )
                logger.info(f"Subscribed to ticker and heartbeats for {self.product_ids}")
                
                # Connection monitoring loop
                # This implements the pattern:
                # while True:
                #     if wsClient.error:
                #         wsClient.close()
                #         wsClient.error = None
                #         wsClient.start()
                #     time.sleep(1)
                while self.running:
                    # Check for errors on the client
                    if hasattr(self.ws_client, 'error') and self.ws_client.error:
                        logger.warning(f"Error detected on client: {self.ws_client.error}")
                        
                        # Close the current connection
                        try:
                            self.ws_client.close()
                        except Exception as e:
                            logger.warning(f"Error while closing connection: {e}")
                        
                        # Clear the error flag
                        self.ws_client.error = None
                        
                        # Increment reconnect counter
                        self.reconnect_count += 1
                        
                        # Check if we've exceeded max reconnects
                        if self.reconnect_count >= self.max_reconnects:
                            logger.critical(f"Exceeded maximum reconnection attempts ({self.max_reconnects}). Stopping.")
                            self.running = False
                            break
                        
                        # Wait before reconnecting
                        logger.info(f"Waiting {self.reconnect_delay} second(s) before reconnecting...")
                        time.sleep(self.reconnect_delay)
                        
                        # Break out of inner loop to restart the connection
                        break
                    
                    # Also check for WebSocket connection health
                    # Some SDKs might not set an error flag, so we check if the connection is still alive
                    if hasattr(self.ws_client, 'socket') and self.ws_client.socket:
                        if not self.ws_client.socket.connected:
                            logger.warning("WebSocket socket disconnected unexpectedly")
                            
                            # Set error flag to trigger reconnection
                            if hasattr(self.ws_client, 'error'):
                                self.ws_client.error = ConnectionError("Socket disconnected")
                            
                            # Increment reconnect counter
                            self.reconnect_count += 1
                            break
                    
                    # Sleep before next error check
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received. Stopping...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Fatal error in WebSocket connection: {e}", exc_info=True)
                
                # Increment reconnect counter
                self.reconnect_count += 1
                
                # Check if we should retry
                if self.reconnect_count >= self.max_reconnects:
                    logger.critical(f"Exceeded maximum reconnection attempts ({self.max_reconnects}). Stopping.")
                    self.running = False
                    break
                
                # Clean up current client
                self.cleanup()
                
                # Wait before retrying
                logger.info(f"Waiting {self.reconnect_delay} second(s) before retrying...")
                time.sleep(self.reconnect_delay)
                continue
        
        # Clean up when exiting the main loop
        self.cleanup()
        logger.info("WebSocket connection handler stopped")
    
    def stop(self) -> None:
        """
        Gracefully stop the WebSocket connection.
        
        This performs proper cleanup:
        - Sets running flag to False to break the main loop
        - Unsubscribes from channels
        - Closes the connection gracefully
        """
        logger.info("Stopping WebSocket connection...")
        self.running = False
        
        if self.ws_client:
            try:
                # Try to unsubscribe before closing
                try:
                    self.ws_client.unsubscribe(
                        product_ids=self.product_ids,
                        channels=["ticker", "heartbeats"]
                    )
                    logger.info("Unsubscribed from channels")
                except Exception as e:
                    logger.warning(f"Error during unsubscribe: {e}")
                
                # Close the connection
                try:
                    self.ws_client.close()
                    logger.info("Connection closed")
                except Exception as e:
                    logger.warning(f"Error during close: {e}")
                
                # Clear error flag
                if hasattr(self.ws_client, 'error'):
                    self.ws_client.error = None
                    
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.ws_client:
            try:
                self.ws_client.close()
            except:
                pass
            self.ws_client = None
    
    def get_error_count(self) -> int:
        """Return the current error count."""
        return self.error_count
    
    def get_reconnect_count(self) -> int:
        """Return the current reconnection count."""
        return self.reconnect_count
    
    def reset_error_count(self) -> None:
        """Reset the error counter."""
        self.error_count = 0
        logger.debug("Error counter reset")





# {
# 'channel': 'ticker', 
# 'timestamp': '2026-05-02T22:33:46.496993622Z', 
# 'sequence_num': 0, 'events': [
# {'type': 'snapshot', 'tickers': [
# {
# 'type': 'ticker', 
# 'product_id': 'XLM-USD', 
# 'price': '0.16039', 
# 'volume_24_h': '14787228.62308827', 
# 'low_24_h': '0.15888', 
# 'high_24_h': '0.16102', 
# 'low_52_w': '0.13612', 
# 'high_52_w': '0.520657', 
# 'price_percent_chg_24_h': '0.06862989767906', 
# 'best_bid': '0.160391', 
# 'best_ask': '0.160392', 
# 'best_bid_quantity': '2090.20104701', 
# 'best_ask_quantity': '6.9'}
# ]}]}


# {'channel': 'subscriptions', 'timestamp': '2026-05-02T22:33:46.497020649Z', 'sequence_num': 1, 'events': [{'subscriptions': {'ticker': ['XLM-USD']}}]}
# {'channel': 'subscriptions', 'timestamp': '2026-05-02T22:33:46.497101681Z', 'sequence_num': 2, 'events': [{'subscriptions': {'heartbeats': ['heartbeats'], 'ticker': ['XLM-USD']}}]}
# {'channel': 'ticker', 'timestamp': '2026-05-02T22:33:46.952591545Z', 'sequence_num': 3, 'events': [{'type': 'update', 'tickers': [{'type': 'ticker', 'product_id': 'XLM-USD', 'price': '0.16039', 'volume_24_h': '14787228.62308827', 'low_24_h': '0.15888', 'high_24_h': '0.16102', 'low_52_w': '0.13612', 'high_52_w': '0.520657', 'price_percent_chg_24_h': '0.06862989767906', 'best_bid': '0.160383', 'best_ask': '0.160392', 'best_bid_quantity': '1861.18431221', 'best_ask_quantity': '6.9'}]}]}
# {'channel': 'ticker', 'timestamp': '2026-05-02T22:33:47.201194817Z', 'sequence_num': 4, 'events': [{'type': 'update', 'tickers': [{'type': 'ticker', 'product_id': 'XLM-USD', 'price': '0.16039', 'volume_24_h': '14787228.62308827', 'low_24_h': '0.15888', 'high_24_h': '0.16102', 'low_52_w': '0.13612', 'high_52_w': '0.520657', 'price_percent_chg_24_h': '0.06862989767906', 'best_bid': '0.160384', 'best_ask': '0.160392', 'best_bid_quantity': '2041.32834967', 'best_ask_quantity': '6.9'}]}]}
# {'channel': 'heartbeats', 'timestamp': '2026-05-02T22:33:47.241911324Z', 'sequence_num': 5, 'events': [{'current_time': '2026-05-02 22:33:47.235014651 +0000 UTC m=+161913.312178269', 'heartbeat_counter': 161913}]}
# {'channel': 'ticker', 'timestamp': '2026-05-02T22:33:47.451867458Z', 'sequence_num': 6, 'events': [{'type': 'update', 'tickers': [{'type': 'ticker', 'product_id': 'XLM-USD', 'price': '0.16039', 'volume_24_h': '14787228.62308827', 'low_24_h': '0.15888', 'high_24_h': '0.16102', 'low_52_w': '0.13612', 'high_52_w': '0.520657', 'price_percent_chg_24_h': '0.06862989767906', 'best_bid': '0.160391', 'best_ask': '0.160392', 'best_bid_quantity': '973.29809', 'best_ask_quantity': '6.9'}]}]}