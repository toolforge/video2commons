/* eslint-env node */
var gulp = require( 'gulp' ),
	concat = require( 'gulp-concat' ),
	htmlmin = require( 'gulp-htmlmin' ),
	nunjucks = require( 'gulp-nunjucks' ),
	rename = require( 'gulp-rename' ),
	uglify = require( 'gulp-uglify' );

gulp.task( 'scripts', function () {
	return gulp
		.src( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ] )
		.pipe( rename( { suffix: '.min' } ) )
		.pipe( uglify() )
		.pipe( gulp.dest( './video2commons/frontend/static/' ) );
} );

gulp.task( 'jinja2', function () {
	return gulp
		.src( [ './video2commons/frontend/templates/**.html', '!./video2commons/frontend/templates/**.min.html' ] )
		.pipe( rename( { suffix: '.min' } ) )
		.pipe( htmlmin( { collapseWhitespace: true, minifyCSS: true } ) )
		.pipe( gulp.dest( './video2commons/frontend/templates/' ) );
} );

gulp.task( 'nunjucks', function () {
	return gulp
		.src( [ './video2commons/frontend/static/templates/**.html' ] )
		.pipe( htmlmin( { collapseWhitespace: true, minifyCSS: true } ) )
		.pipe( nunjucks.precompile() )
		.pipe( concat( '../templates.min.js' ) )
		.pipe( uglify() )
		.pipe( gulp.dest( './video2commons/frontend/static/templates' ) );
} );

gulp.task( 'watch', function () {
	var changeevent = function ( event ) {
		// eslint-disable-next-line no-console
		console.log( 'File ' + event.path + ' was ' + event.type + ', running tasks...' );
	};
	gulp.watch( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ], [ 'scripts' ] )
		.on( 'change', changeevent );

	gulp.watch( [ './video2commons/frontend/templates/**.html', '!./video2commons/frontend/templates/**.min.html' ], [ 'jinja2' ] )
		.on( 'change', changeevent );

	gulp.watch( [ './video2commons/frontend/static/templates/**.html' ], [ 'nunjucks' ] )
		.on( 'change', changeevent );
} );

gulp.task( 'default', [ 'scripts', 'jinja2', 'nunjucks', 'watch' ] );
