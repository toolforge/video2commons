/* eslint-env node */
/* eslint no-console: 0 */

/* ===== Globals Declaration ===== */

const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { createClient } = require('redis');
const request = require('request');
const config = require('../config.json');

const port = parseInt(process.env.PORT, 10);
const app = express();
const server = http.createServer(app);
const io = new Server(server, {
    cors: {
        origin: `https:${config.webfrontend_uri}`,
        methods: ["GET", "POST"],
        credentials: true
    }
});

const redisParams = {
	url: `redis://${config.redis_host}`,
	password: config.redis_pw,
	database: 3
};

// Redis clients
const redisConnection = createClient(redisParams);
const redisSubscription = createClient(redisParams);

/* ===== Redis Error Handling ===== */
redisConnection.on('error', (err) => console.error('Redis Connection Error:', err));
redisSubscription.on('error', (err) => console.error('Redis Subscription Error:', err));

(async () => {
	await redisConnection.connect();
	await redisSubscription.connect();
	console.log('Connected to Redis');
})();

/* ===== HTTP / Socket.io Request Handling ===== */

app.all( '*', ( req, res ) => {
	res.redirect( config.webfrontend_uri );
} );

io.on( 'connection', ( socket ) => {
	console.log(`[${new Date()}] Connected: ${socket.id}`);
	socket.on( 'auth', async ( data ) => {
		try {
			const sessionKey = await redisConnection.get(`iosession:${data.iosession}`);
			if (!sessionKey) return socket.disconnect();

			const sessionData = await redisConnection.get(`session:${sessionKey}`);
			if (!sessionData) return socket.disconnect();

			const session = JSON.parse(sessionData);
			// eslint-disable-next-line no-underscore-dangle
			if (data._csrf_token !== session._csrf_token) return socket.disconnect();

			const jar = request.jar();
			const cookie = request.cookie(`v2c-session=${sessionKey}`);
			const url = `https:${config.webfrontend_uri}/api/status`;
			jar.setCookie(cookie, url);

			request({ url, jar, headers: {
					'User-Agent': 'video2commons-socketio',
					// 'X-V2C-Session-Bypass': config.session_key
				} }, (error, response, body) => {
					if ( error || response.statusCode !== 200 ) {
						return socket.disconnect();
					}
					const status = JSON.parse( body );

					socket.emit( 'status', status );
					socket.join( status.rooms );
				} );
		} catch (err) {
			console.error('Auth error:', err);
			socket.disconnect();
		}
	} );

	socket.on( 'disconnect', () => {
		console.log(`[${new Date()}] Disconnected: ${socket.id}`);
	} );
} );

server.listen(port, () => {
	console.log(`Server running on port ${port}`);
});

/* ===== Socket.io Client Notification ===== */

const forEachSocketInRoom = async ( room, cb ) => {
	const sockets = await io.in(room).fetchSockets();
	sockets.forEach(cb);
};

const addTask = ( taskId, user ) => {
	forEachSocketInRoom( `tasks:${user}`, ( socket ) => socket.join( taskid ) );
	forEachSocketInRoom( 'alltasks', ( socket ) => socket.join( taskid ) );
};

const updateTask = async ( taskId, data ) => {
	if ( data ) {
		io.in( taskId ).emit( 'update', taskId, data );
	} else {
		const sockets = await io.in(taskId).fetchSockets();
		if (sockets.length) {
			request( {
				url: `https:${config.webfrontend_uri}/api/status-single?task=${taskId}`,
				headers: {
					'User-Agent': 'video2commons-socketio',
					// 'X-V2C-Session-Bypass': config.session_key
				}
			}, ( error, response, body ) => {
				if ( error || response.statusCode !== 200 ) {
					console.log(`Failed to fetch status for task ${taskId}`);
					return;
				}
				const result = JSON.parse( body );
				io.in( taskId ).emit( 'update', taskId, result.value );
			} );
		}
	}
};

const removeTask = ( taskId ) => {
	io.in( taskId ).emit( 'remove', taskId );
	forEachSocketInRoom( taskId, ( socket ) => socket.leave( taskId ) );
};

/* ===== Redis Subscription ===== */

(async () => {
	await redisSubscription.pSubscribe('__keyspace@?__:*', (message, channel) => {
		const match = /^__keyspace@(\d)__:(.+)$/.exec(channel);
		if (match) {
			const db = match[ 1 ];
			const key = match[ 2 ];
			const action = message;

			if ( db === '1' && key.startsWith( 'celery-task-meta-' ) ) {
				const id = key.slice( 'celery-task-meta-'.length );
				if ( action === 'set' ) {
					updatetask( id );
				} else if ( action === 'expired' ) {
					removetask( id );
				}
			}
		}
	} );

	await redisSubscription.pSubscribe('v2cnotif:*', (message, channel) => {
		const type = channel.slice('v2cnotif:'.length);
		const data = JSON.parse(message);

		if ( type === 'add' ) {
			addtask( data.taskid, data.user );
		} else if ( type === 'update' ) {
			updatetask( data.taskid, data.data );
		} else if ( type === 'remove' ) {
			removetask( data.taskid );
		}
	} );
})();

