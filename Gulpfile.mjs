import gulp from 'gulp';
import concat from 'gulp-concat';
import htmlmin from 'gulp-htmlmin';
import rename from 'gulp-rename';
import uglify from 'gulp-uglify';
import {nunjucksPrecompile} from 'gulp-nunjucks';
/* eslint-env node */

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
		.pipe( nunjucksPrecompile() )
		.pipe( concat( '../templates.min.js' ) )
		.pipe( uglify() )
		.pipe( gulp.dest( './video2commons/frontend/static/templates' ) );
} );

gulp.task( 'watch', function () {
	var changeevent = function ( event ) {
		// eslint-disable-next-line no-console
		console.log( 'File ' + event.path + ' was ' + event.type + ', running tasks...' );
	};
	gulp.watch( [ './video2commons/frontend/static/*.js', '!./video2commons/frontend/static/*.min.js' ],  gulp.series('scripts') )
		.on( 'change', changeevent );

	gulp.watch( [ './video2commons/frontend/templates/**.html', '!./video2commons/frontend/templates/**.min.html' ], gulp.series('jinja2') )
		.on( 'change', changeevent );

	gulp.watch( [ './video2commons/frontend/static/templates/**.html' ], gulp.series('nunjucks') )
		.on( 'change', changeevent );
} );

gulp.task( 'build', gulp.series( 'scripts', 'jinja2', 'nunjucks' ));

gulp.task( 'default', gulp.series( 'build', 'watch' ));
