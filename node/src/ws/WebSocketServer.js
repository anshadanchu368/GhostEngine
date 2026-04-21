import { WebSocketServer as WsServer } from 'ws';
import broadcaster from './JobBroadcaster.js';
import logger from '../logger.js';

export function createWebSocketServer(httpServer) {
  const wss = new WsServer({ server: httpServer });

  wss.on('connection', (ws, req) => {
    const clientIp = req.socket.remoteAddress;
    logger.info({ client_ip: clientIp }, 'WebSocket client connected');
    broadcaster.addClient(ws);

    ws.on('error', (err) => {
      logger.error({ client_ip: clientIp, err: err.message }, 'WebSocket error');
    });

    ws.on('close', () => {
      logger.info({ client_ip: clientIp }, 'WebSocket client disconnected');
    });
  });

  return wss;
}
