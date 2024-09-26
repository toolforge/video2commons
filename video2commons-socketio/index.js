/* eslint-env node */
/* eslint no-console: 0 */

/* ===== Globals Declaration ===== */

var axios = require( 'axios' ),
	express = require( 'express' ),
	http = require( 'http' ),
	io = require( 'socket.io' )(),
	redis = require( 'redis' ),
	tough = require('tough-cookie');

var port = parseInt( process.env.PORT, 10 ),
	config = require( '../config.json' );

var app = express(),
	redisparams = {
		host: config.redis_host,
		password: config.redis_pw,
		db: 3
	};

var redisconnection = redis.createClient( redisparams ),
	redissubscription = redis.createClient( redisparams );

/* ===== HTTP / Socket.io Request Handling ===== */

app.all( '*', function ( req, res /* , next */ ) {
	res.redirect( config.webfrontend_uri );
} );

io.on( 'connection', function ( socket ) {
	console.log( '[' + new Date() + '] Connected: ' + socket.id );
	socket.on( 'auth', function ( data ) {
		redisconnection.get( 'iosession:' + data.iosession, function ( err, sessionkey ) {
			if ( sessionkey === null ) {
				socket.disconnect();
				return;
			}
			redisconnection.get( 'session:' + sessionkey, function ( err, sessiondata ) {
				if ( sessiondata === null ) {
					socket.disconnect();
					return;
				}

				var session = JSON.parse( sessiondata );
				// eslint-disable-next-line no-underscore-dangle
				if ( data._csrf_token !== session._csrf_token ) {
					socket.disconnect();
					return;
				}

				var j = new tough.CookieJar();
				var domain = 'https:' + config.webfrontend_uri
				var cookie = new tough.Cookie({ key: 'v2c-session', value: sessionkey, domain: domain });
				var url = domain + 'api/status';
				j.setCookieSync( cookie.toString(), url );
				axios( {
					url: url,
					jar: j,
					withCredentials: true,
					headers: {
						'User-Agent': 'video2commons-socketio'
						// 'X-V2C-Session-Bypass': config.session_key
					}
				} ).then ( response => {
					if ( response.status !== 200 ) {
						socket.disconnect();
						return;
					}
					var status = response.data;

					socket.emit( 'status', status );
					socket.join( status.rooms );
				} ).catch ( error => {
					socket.disconnect();
				} );
			} );
		} );
	} );

	socket.on( 'disconnect', function () {
		console.log( '[' + new Date() + '] Disconnected: ' + socket.id );
	} );
} );

io.listen( http.createServer( app ).listen( port ) );

/* ===== Socket.io Client Notification ===== */

var forEachSocketInRoom = function ( room, cb ) {
	var ns = io.in( room );
	ns.clients( function ( error, clients ) {
		if ( error ) {
			throw error;
		}
		clients.forEach( function ( clientId ) {
			cb( ns.connected[ clientId ] );
		} );
	} );
};

var addtask = function ( taskid, user ) {
		forEachSocketInRoom( 'tasks:' + user, function ( socket ) { socket.join( taskid ); } );
		forEachSocketInRoom( 'alltasks', function ( socket ) { socket.join( taskid ); } );
	},
	updatetask = function ( taskid, data ) {
		if ( data ) {
			io.in( taskid ).emit( 'update', taskid, data );
		} else {
			// Do nothing if room is empty
			io.in( taskid ).clients( function ( error, clients ) {
				if ( error ) {
					throw error;
				} else if ( clients ) {
					request( {
						url: 'https:' + config.webfrontend_uri + 'api/status-single?task=' + taskid,
						headers: {
							'User-Agent': 'video2commons-socketio',
							'X-V2C-Session-Bypass': config.session_key
						}
					}, function ( error, response, body ) {
						if ( error || response.statusCode !== 200 ) {
							console.log( 'failed status fetching for ' + taskid );
							return;
						}
						var data = JSON.parse( body );
						io.in( taskid ).emit( 'update', taskid, data.value );
					} );
				}
			} );
		}
	},
	removetask = function ( taskid ) {
		io.in( taskid ).emit( 'remove', taskid );
		forEachSocketInRoom( taskid, function ( socket ) { socket.leave( taskid ); } );
	};

redisconnection.on( 'error', function ( err ) {
	console.log( 'Error: ' + err );
} );

/* ===== Redis Subscription ===== */

redissubscription.psubscribe( '__keyspace@?__:*' );
redissubscription.on( 'pmessage', function ( pattern, channel, message ) {
	if ( pattern !== '__keyspace@?__:*' ) {
		return;
	}
	var match = /^__keyspace@(\d)__:(.+)$/.exec( channel ),
		db = match[ 1 ],
		key = match[ 2 ],
		action = message;

	if ( db === '1' && key.startsWith( 'celery-task-meta-' ) ) {
		var id = key.slice( 'celery-task-meta-'.length );
		if ( action === 'set' ) {
			updatetask( id );
		} else if ( action === 'expired' ) {
			removetask( id );
		}
	}
} );

redissubscription.psubscribe( 'v2cnotif:*' );
redissubscription.on( 'pmessage', function ( pattern, channel, message ) {
	if ( pattern !== 'v2cnotif:*' ) {
		return;
	}
	var type = channel.slice( 'v2cnotif:'.length ),
		data = JSON.parse( message );
	if ( type === 'add' ) {
		addtask( data.taskid, data.user );
	} else if ( type === 'update' ) {
		updatetask( data.taskid, data.data );
	} else if ( type === 'remove' ) {
		removetask( data.taskid );
	}
} );
