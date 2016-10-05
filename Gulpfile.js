/* eslint-env node */
var gulp = require( 'gulp' );
var uglify = require( 'gulp-uglify' );
var rename = require( 'gulp-rename' );

gulp.task( 'scripts', function() {
	return gulp
		.src( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ] )
		.pipe( rename( { suffix: '.min' } ) )
		.pipe( uglify() )
		.pipe( gulp.dest( './video2commons/frontend/static/' ) );
} );

gulp.task( 'watch', function() {
	var changeevent = function( event ) {
		console.log( 'File ' + event.path + ' was ' + event.type + ', running tasks...' );
	};
	gulp.watch( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ], [ 'scripts' ] )
		.on( 'change', changeevent );
} );

gulp.task( 'default', [ 'scripts', 'watch' ] );
