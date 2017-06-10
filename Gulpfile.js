/* eslint-env node */
var gulp = require( 'gulp' );
var uglify = require( 'gulp-uglify' );
var rename = require( 'gulp-rename' );
var htmlmin = require( 'gulp-htmlmin' );

gulp.task( 'scripts', function () {
	return gulp
		.src( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ] )
		.pipe( rename( { suffix: '.min' } ) )
		.pipe( uglify() )
		.pipe( gulp.dest( './video2commons/frontend/static/' ) );
} );

gulp.task( 'html', function () {
	return gulp
		.src( [ './video2commons/frontend/**/*.html', '!./video2commons/frontend/**/*.min.html' ] )
		.pipe( rename( { suffix: '.min' } ) )
		.pipe( htmlmin( { collapseWhitespace: true, minifyCSS: true } ) )
		.pipe( gulp.dest( './video2commons/frontend/' ) );
} );

gulp.task( 'watch', function () {
	var changeevent = function ( event ) {
		console.log( 'File ' + event.path + ' was ' + event.type + ', running tasks...' );  // eslint-disable-line no-console
	};
	gulp.watch( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ], [ 'scripts' ] )
		.on( 'change', changeevent );

	gulp.watch( [ './video2commons/frontend/**/*.html', '!./video2commons/frontend/**/*.min.html' ], [ 'html' ] )
		.on( 'change', changeevent );
} );

gulp.task( 'default', [ 'scripts', 'html', 'watch' ] );
