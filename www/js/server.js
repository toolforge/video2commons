/* eslint-env node */
var fs = require( 'fs' ),
	access = fs.createWriteStream( '/data/project/video2commons-socketio/node.log' );
process.stdout.write = process.stderr.write = access.write.bind( access );

process.on( 'uncaughtException', function ( err ) {
	fs.writeSync(
		fs.openSync( '/data/project/video2commons-socketio/node.log', 'w' ),
		'Caught exception: ' + err + '\n' + err.stack + '\n'
	);
	process.exit( 1 );
} );

require( '../../video2commons-socketio/index.js' );
