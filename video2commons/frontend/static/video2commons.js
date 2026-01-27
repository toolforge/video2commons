/* globals nunjucks: false, io: false, Qs: false */
( function ( $ ) {
	'use strict';

	var config = window.config,
		i18n = window.i18n,
		loaderImage = '<img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">',
		rtl = i18n[ '@dir' ] === 'rtl',
		htmlContent = {
			abortbutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right"><span class="glyphicon glyphicon-remove"></span> ' + nunjucks.lib.escape( i18n.abort ) + '</button>',
			removebutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right remove-btn"><span class="glyphicon glyphicon-trash"></span> ' + nunjucks.lib.escape( i18n.remove ) + '</button>',
			restartbutton: '<button type="button" class="btn btn-xs flip pull-right restart-btn"><span class="glyphicon glyphicon-repeat"></span> ' + nunjucks.lib.escape( i18n.restart ) + '</button>',
			loading: '<center>' + loaderImage + '&nbsp;&nbsp;' + nunjucks.lib.escape( i18n.loading ) + '</center>',
			errorDisconnect: '<div class="alert alert-danger">' + nunjucks.lib.escape( i18n.errorDisconnect ) + '</div>',
			yourTasks: '<h4>' + nunjucks.lib.escape( i18n.yourTasks ) + '</h4><table id="tasktable" class="table"><colgroup><col style="width: 20%;"/><col style="width: 10%;"/><col style="width: 40%;"/><col style="width: 30%;"/></colgroup><tbody></tbody></table>',
			workers: '<h4>' + nunjucks.lib.escape( i18n.workers ) + '</h4>',
			capacity: rtl ? `<div><span id="capacity">...</span> ${i18n.capacity}</div>` : `<div>${i18n.capacity} <span id="capacity">...</span></div>`,
			utilization: rtl ? `<div><span id="utilization">...</span> ${i18n.utilization}</div>` : `<div>${i18n.utilization} <span id="utilization">...</span></div>`,
			pending: rtl ? `<div><span id="pending">...</span> ${i18n.pending}</div>` : `<div>${i18n.pending} <span id="pending">...</span></div>`,
			addTask: '<input class="btn btn-primary btn-md" type="button" accesskey="n" value="' + nunjucks.lib.escape( i18n.addTask ) + '">',
			requestServerSide: '<a class="btn btn-primary btn-success btn-md flip pull-right disabled" id="ssubtn">' + nunjucks.lib.escape( i18n.createServerSide ) + '</a>',
			progressbar: '<div class="progress"><div class="progress-bar" role="progressbar"></div></div>',
			prevbutton: '<span class="glyphicon glyphicon-chevron-' + ( rtl ? 'right' : 'left' ) + '"></span> ' + nunjucks.lib.escape( i18n.back ),
			nextbutton: nunjucks.lib.escape( i18n.next ) + ' <span class="glyphicon glyphicon-chevron-' + ( rtl ? 'left' : 'right' ) + '"></span>',
			confirmbutton: nunjucks.lib.escape( i18n.confirm )
		},
		ssuTemplate = 'Please upload these file(s) to Wikimedia Commons:\n\n**URLs**\n\n{{{ urls }}}\n\n//Description files are available too: append `.txt` to the URLs.//\n\n**Checksums**\n\n| **File** | **MD5** |\n{{{ checksums }}}\n\nThank you!',
		csrfToken = '',
		nunjucksEnv = new nunjucks.Environment()
			.addGlobal( 'config', config )
			.addGlobal( '_', function ( key ) { return i18n[ key ]; } )
			.addFilter( 'process_link', function ( text ) {
				var regex = /\{\{#a\}\}(.*?)\{\{\/a\}\}/g,
					last = 0,
					processed = '',
					execResult,
					a = function ( inner ) {
						if ( inner[ 0 ] === '#' ) {
							var splitloc = inner.indexOf( '|' );
							if ( splitloc < 0 ) {
								// XSS prevention: Nasty attribute escaping -- allow alphanumerics and hyphens only here
								if ( /^[a-z0-9-]+$/i.test( inner.slice( 1 ) ) ) {
									return '<a id="' + inner.slice( 1 ) + '"></a>';
								}
							} else {
								if ( /^[a-z0-9-]+$/i.test( inner.substring( 1, splitloc ) ) ) {
									return '<a id="' + inner.substring( 1, splitloc ) + '">' + nunjucks.lib.escape( inner.slice( splitloc + 1 ) ) + '</a>';
								}
							}
						}
						return '<a>' + nunjucks.lib.escape( inner ) + '</a>';
					};

				while ( ( execResult = regex.exec( text ) ) !== null ) {
					processed += nunjucks.lib.escape( text.substring( last, execResult.index ) );
					processed += a( execResult[ 1 ] );
					last = regex.lastIndex;
				}

				processed += nunjucks.lib.escape( text.slice( last ) );

				return new nunjucks.runtime.SafeString( processed );
			} );

	var $addTaskDialog, newTaskData, newTaskDataQS, SSUs, username;

	/**
	 * Validate date category names.
	 *
	 * This function ensures that dates are valid and match these patterns:
	 *
	 * - "Videos of YYYY"
	 * - "Videos taken on YYYY-MM-DD"
	 *
	 * @param {string} value The date category value to validate.
	 * @return {object} Object with valid (boolean), value (string|null), and error (string|undefined).
	 */
	function validateDateCategory( value ) {
		// Dates are optional, so pass through as valid if no value is given.
		if ( !value ) {
			return { valid: true, value: null };
		}

		// Validate names that match the "Videos of YYYY" pattern.
		const yearMatch = value.match( /^Videos of (\d{4})$/ );
		if ( yearMatch ) {
			const year = parseInt( yearMatch[ 1 ], 10 );
			const currentYear = new Date().getFullYear();

			if ( year > currentYear ) {
				return { valid: false, error: i18n[ 'datecategory-error-future-year' ] };
			}

			return { valid: true, value };
		}

		// Validate names that match the "Videos taken on YYYY-MM-DD" pattern.
		const dateMatch = value.match( /^Videos taken on (\d{4})-(\d{2})-(\d{2})$/ );
		if ( dateMatch ) {
			const year = parseInt( dateMatch[ 1 ], 10 );
			const month = parseInt( dateMatch[ 2 ], 10 );
			const day = parseInt( dateMatch[ 3 ], 10 );
			const date = new Date( year, month - 1, day );
			const now = new Date();

			if (
				date.getFullYear() !== year
				|| date.getMonth() !== month - 1
				|| date.getDate() !== day
				|| date > now
			) {
				return { valid: false, error: i18n[ 'datecategory-error-invalid-date' ] };
			}

			return { valid: true, value };
		}

		return { valid: false, error: i18n[ 'datecategory-error-format' ] };
	}

	/**
	 * Get the placeholder text for the date category field.
	 *
	 * @param {object} source The source data object (newTaskData or a video object).
	 * @return {string} The placeholder text with example formats.
	 */
	function getDateCategoryPlaceholder( source ) {
		const now = new Date();
		const currentDate = now.toISOString().split( 'T' )[ 0 ];
		const dateStr = source.date || currentDate;
		const yearStr = dateStr.split( '-' )[ 0 ];

		return i18n[ 'datecategory-placeholder' ].replace( '$1', yearStr ).replace( '$2', dateStr );
	}

	/**
	 * Get the default value for the date category field.
	 *
	 * @param {object} source The source data object (newTaskData or a video object).
	 * @return {string} The default value.
	 */
	function getDateCategoryDefault( source ) {
		const now = new Date();
		const currentDate = now.toISOString().split( 'T' )[ 0 ];
		const dateStr = source.date || currentDate;
		const yearStr = dateStr.split( '-' )[ 0 ];

		return `Videos of ${yearStr}`;
	}

	/**
	 * Generate datalist options for the date category field.
	 *
	 * @param {object} source The source data object (newTaskData or a video object).
	 * @return {Array} Array of option strings.
	 */
	function getDateCategoryOptions( source ) {
		const now = new Date();
		const currentDate = now.toISOString().split( 'T' )[ 0 ];
		const dateStr = source.date || currentDate;
		const yearStr = dateStr.split( '-' )[ 0 ];

		return [
			`Videos of ${yearStr}`,
			`Videos taken on ${dateStr}`
		];
	}

	const form = {
		/**
		 * Get the data from the source form in the new task dialog.
		 */
		getSourceData: function () {
			return {
				url: $addTaskDialog.find( '#url' ).val(),
				video: $addTaskDialog.find( '#video' ).is( ':checked' ),
				audio: $addTaskDialog.find( '#audio' ).is( ':checked' ),
				subtitles: $addTaskDialog.find( '#subtitles' ).is( ':checked' )
			};
		},

		/**
		 * Get the data from the target form in the new task dialog.
		 */
		getTargetData: function () {
			return {
				filename: $addTaskDialog.find( '#filename' ).val().trim(),
				format: $addTaskDialog.find( '#format' ).val(),
				filedesc: $addTaskDialog.find( '#filedesc' ).val(),
				dateCategory: $addTaskDialog.find( '#dateCategory' ).val().trim()
			};
		},

		/**
		 * Get the data from the playlist form in the new task dialog.
		 */
		getPlaylistData: function () {
			const selectedVideos = [];

			$addTaskDialog.find( '.video-select:checked' ).each( function () {
				const index = parseInt( $( this ).val(), 10 );
				const video = newTaskData.videos[ index ];
				selectedVideos.push( video );
			} );

			return selectedVideos;
		},
	};

	const api = {
		/**
		 * Start a new video transcoding task.
		 *
		 * @param {object} task The details of the task to start.
		 * @return {jQuery.Deferred} Resolves when the API call is complete.
		 */
		startTask: function ( task ) {
			return video2commons.apiPost( 'task/run', task );
		},

		/**
		 * Update valid output formats for the input video.
		 *
		 * @param {boolean} keepVideo Whether the video is kept.
		 * @param {boolean} keepAudio Whether the audio is kept.
		 * @return {jQuery.Deferred} Resolves if the formats are valid.
		 */
		updateFormats: function ( keepVideo, keepAudio ) {
			if (
				newTaskData.formats.length > 0 &&
				keepVideo === newTaskData.video &&
				keepAudio === newTaskData.audio
			) {
				return $.when();
			}

			return video2commons.askAPI(
				'listformats',
				{ video: keepVideo, audio: keepAudio },
				[ 'video', 'audio', 'format', 'formats' ]
			);
		},

		/**
		 * Validate the input video URL and generate a description for it.
		 *
		 * @param {string} url The URL to check.
		 * @return {jQuery.Deferred} Resolves if the URL is valid.
		 */
		updateUrl: function ( url ) {
			if ( !url ) {
				return $.Deferred()
					.reject( 'URL cannot be empty!' )
					.promise();
			}

			if ( url === newTaskData.url && newTaskData.initialFilenameValidated ) {
				return $.when();
			}

			// Generate a description for files that are from the filesystem.
			var uploadedFile = newTaskData.uploadedFile[ url ];
			if ( uploadedFile ) {
				newTaskData.url = url;
				return video2commons.askAPI( 'makedesc', {
					filename: uploadedFile.name || ''
				}, [ 'extractor', 'filedesc', 'filename' ] );
			}

			// Validate that the video at the URL hasn't already been uploaded
			// to Commons, and if it hasn't, extract its metadata.
			return video2commons.askAPI( 'validateurl', { url }, [ 'entity_url' ] )
				.then( function ( data ) {
					if ( data.entity_url ) {
						return $.Deferred()
							.reject( 'This video has already been uploaded: ' + data.entity_url )
							.promise();
					}
					return video2commons.askAPI( 'extracturl', { url }, [
						'type',
						'id',
						'title',
						'url',
						'date',
						'extractor',
						'filedesc',
						'filename',
						'videos'
					] ).then( () => {
						newTaskData.initialFilenameValidated = true;
					} );
				} )
				.then( function () {
					if ( newTaskData.type === 'playlist' ) {
						newTaskData.videos.forEach( ( video ) => {
							video.format = newTaskData.format;
							video.dateCategory = getDateCategoryDefault( video );
						} );
					} else {
						newTaskData.dateCategory = getDateCategoryDefault( newTaskData );
					}
				} );
		},

		/**
		 * Check if the given filename is valid and unique.
		 *
		 * @param {string} filename The filename to check.
		 * @param {object|null} object The object to update.
		 * @return {jQuery.Deferred} Resolves if the filename is valid.
		 */
		updateFilename: function ( filename, object=null ) {
			if ( object == null ) {
				object = newTaskData;
			}

			if ( !filename ) {
				return $.Deferred()
					.reject( 'Filename cannot be empty!' )
					.promise();
			}

			if ( filename === object.filename && object.initialFilenameValidated ) {
				return $.when();
			}

			return video2commons.askAPI( 'validatefilename', { filename }, [], object )
				.then( function () {
					return video2commons.askAPI(
						'validatefilenameunique', { filename }, [ 'filename' ], object
					);
				} )
				.then( function () {
					object.initialFilenameValidated = true;
				} );
		},

		/**
		 * Check if the given file description is valid.
		 *
		 * @param {string} filedesc The file description to check.
		 * @param {object|null} object The object to update.
		 * @return {jQuery.Deferred} Resolves if the file description is valid.
		 */
		updateFiledesc: function ( filedesc, object=null ) {
			if ( object == null ) {
				object = newTaskData;
			}

			if ( !filedesc ) {
				return $.Deferred()
					.reject( 'Decription cannot be empty!' )
					.promise();
			}

			if ( filedesc === object.filedesc && object.initialFiledescValidated ) {
				return $.when();
			}

			return video2commons.askAPI( 'validatefiledesc', { filedesc }, [ 'filedesc' ], object )
				.then( function () {
					object.initialFiledescValidated = true;
				} );
		},

		/**
		 * Validate that a video URL is valid and not already on the wiki.
		 *
		 * @param {string} url The URL to check.
		 * @return {jQuery.Deferred} Resolves if the URL is valid.
		 */
		validateUrl: function ( url ) {
			return video2commons.askAPI( 'validateurl', { url }, [] )
				.then( ( data ) => {
					if ( data.entity_url ) {
						return $.Deferred()
							.reject( 'This video has already been uploaded: ' + data.entity_url )
							.promise();
					}
				} );
		}
	};

	const steps = {
		source: function () {
			const data = form.getSourceData();
			newTaskData.subtitles = data.subtitles;
			newTaskData.selectedVideos = [];

			return $.when(
				api.updateFormats( data.video, data.audio ),
				api.updateUrl( data.url )
			).then( () => {
				if ( newTaskData.type === 'playlist' ) {
					newTaskData.nextStep = 'playlist';
				} else {
					newTaskData.nextStep = 'target';
				}
			} );
		},

		playlist: function () {
			const selectedVideos = form.getPlaylistData();

			if ( selectedVideos.length === 0 ) {
				return $.Deferred()
					.reject( 'Please select at least one video to upload!' )
					.promise();
			}

			const tasks = [
				...selectedVideos.map( ( video ) => () => api.updateFilename( video.filename, video ) ),
				...selectedVideos.map( ( video ) => () => api.updateFiledesc( video.filedesc, video ) ),
				...selectedVideos.map( ( video ) => () => api.validateUrl( video.url ) )
			];
			return $.when( video2commons.runWithConcurrency( tasks ) )
				.then( ( results ) => {
					const errors = results.filter( ( result ) => !!result?.error );
					if ( errors.length > 0 ) {
						return $.Deferred()
							.reject( errors.map( ( result ) => result.error ).join( '\n\n' ) )
							.promise();
					}

					newTaskData.selectedVideos = selectedVideos;
					newTaskData.nextStep = 'confirm';
				} );
		},

		target: function () {
			const data = form.getTargetData();

			const object = newTaskData.type === 'playlist'
				? newTaskData.videos[ newTaskData.editingVideoIndex ]
				: newTaskData;

			object.format = data.format;

			const dateCategoryResult = validateDateCategory( data.dateCategory );
			if ( !dateCategoryResult.valid ) {
				return $.Deferred()
					.reject( dateCategoryResult.error )
					.promise();
			}
			object.dateCategory = dateCategoryResult.value;

			return $.when(
				api.updateFilename( data.filename, object ),
				api.updateFiledesc( data.filedesc, object )
			).then( () => {
				if ( newTaskData.type === 'playlist' ) {
					newTaskData.nextStep = 'playlist';
				} else {
					newTaskData.nextStep = 'confirm';
				}
			} );
		},

		confirm: function () {
			return $.when().then( () => {
				newTaskData.nextStep = null;
			} );
		}
	};

	var video2commons = window.video2commons = {
		init: function () {
			$( '#content' )
				.html( htmlContent.loading );

			SSUs = {};

			video2commons.loadCsrf( video2commons.checkStatus );

			$( window ).on( 'beforeunload', function ( e ) {
				if ( $addTaskDialog && $addTaskDialog.is( ':visible' ) ) {
					e.preventDefault();
					e.returnValue = '';
					return '';
				}
			} );

			// If location.hash matches, fire up a new task dialog
			var rePrefill = /^#?!(https?:\/\/.+)/;
			if ( rePrefill.test( window.location.hash ) ) {
				video2commons.addTask( {
					url: window.location.hash.match( rePrefill )[ 1 ]
				} );
			} else if ( window.location.search.slice( 1 ) ) {
				newTaskDataQS = Qs.parse( window.location.search.slice( 1 ) );
				video2commons.addTask( {
					url: newTaskDataQS.url
				} );
			}
		},

		loadCsrf: function ( cb ) {
			$.get( 'api/csrf' )
				.done( function ( data ) {
					csrfToken = data.csrf;
					cb();
				} );
		},

		// Functions related to showing running/finished tasks
		checkStatus: function () {
			if ( config.socketio_uri && window.WebSocket && window.io ) {
				video2commons.checkStatusSocket();
			} else {
				video2commons.checkStatusLegacy();
			}
		},

		checkStatusSocket: function () {
			if ( window.socket ) {
				return;
			}

			var socketmatch = config.socketio_uri.match( /^((?:(?:https?:)?\/\/)?[^/]+)(\/.*)$/ ),
				sockethost = socketmatch[ 1 ],
				socketpath = socketmatch[ 2 ],
				socket = window.socket = io( sockethost, { path: socketpath } );

			socket.on( 'connect', function () {
				$.get( 'api/iosession' )
					.done( function ( data ) {
						socket.emit( 'auth', {
							iosession: data.iosession,
							_csrf_token: csrfToken // eslint-disable-line camelcase
						} );
					} );
			} );

			socket.on( 'status', function ( data ) {
				video2commons.alterTaskTableBoilerplate( function () {
					video2commons.populateResults( data );
				} );
			} );
			socket.on( 'update', function ( taskid, data ) {
				video2commons.alterTaskTableBoilerplate( function () {
					video2commons.updateTask( data );
				} );
			} );
			socket.on( 'remove', function ( taskid ) {
				video2commons.alterTaskTableBoilerplate( function () {
					$( '#task-' + taskid ).remove();
				} );
			} );
		},

		checkStatusLegacy: function () {
			if ( window.lastStatusCheck ) {
				clearTimeout( window.lastStatusCheck );
			}
			var url = 'api/status';
			$.get( url )
				.done( function ( data ) {
					video2commons.alterTaskTableBoilerplate( function () { video2commons.populateResults( data ); } );
					window.lastStatusCheck = setTimeout( video2commons.checkStatusLegacy, 5000 );
				} )
				.fail( function () {
					$( '#content' )
						.html( htmlContent.errorDisconnect );
				} );
		},

		setupTables: function () {
			$( '#content' ).empty();

			$( '#content' ).append( htmlContent.workers );
			$( '#content' ).append( htmlContent.capacity );
			$( '#content' ).append( htmlContent.utilization );
			$( '#content' ).append( htmlContent.pending );
			$( '#content' ).append( htmlContent.yourTasks );

			const addButton = $( htmlContent.addTask );
			$( '#content' ).append( addButton );
			addButton.click( function () {
				video2commons.addTask();
			} );

			const ssuButton = $( htmlContent.requestServerSide );
			$( '#content' ).append( ssuButton.hide() );
		},

		alterTaskTableBoilerplate: function ( cb ) {
			if ( !$( '#tasktable' ).length ) {
				video2commons.setupTables();
			}

			var isatbottom = ( window.innerHeight + window.scrollY ) >= document.body.offsetHeight;

			cb();

			if ( !$.isEmptyObject( SSUs ) ) {
				$( '#ssubtn' )
					.removeClass( 'disabled' )
					.show()
					.attr( 'href', video2commons.makeSSULink( SSUs ) );
			} else {
				$( '#ssubtn' )
					.addClass( 'disabled' )
					.hide();
			}

			if ( isatbottom ) {
				window.scrollTo( 0, document.body.scrollHeight );
			}
		},

		populateResults: function ( data ) {
			username = data.username;

			var table = $( '#tasktable > tbody' ),
				ids = [];

			// add & update
			$.each( data.values, function ( i, val ) {
				video2commons.updateTask( val );
				ids.push( val.id );
			} );

			// remove extras
			table.find( '> tr' )
				.each( function () {
					var $row = $( this ),
						id = video2commons.getTaskIDFromDOMID( $row.attr( 'id' ) );
					if ( ids.indexOf( id ) < 0 ) {
						$row.remove();
					}
				} );


			if ( data.stats ) {
				$( '#capacity' ).text( `${data.stats.processing} / ${data.stats.capacity}` );
				$( '#utilization' ).text( `${Math.round(data.stats.utilization * 100)}%` );
				$( '#pending' ).text( `${data.stats.pending}` );
			} else {
				$( '#capacity' ).text( 'N/A' );
				$( '#utilization' ).text( 'N/A' );
				$( '#pending' ).text( 'N/A' );
			}
		},

		updateTask: function ( val ) {
			var table = $( '#tasktable > tbody' );

			var id = 'task-' + val.id,
				$row = $( '#' + id );
			if ( !$row.length ) {
				$( '#task-new' ).remove();
				$row = $( '<tr />' );
				$row.attr( {
					id: id,
					status: val.status
				} );
				table.append( $row );
				video2commons.setupTaskRow( $row, id, val.status );
			} else if ( $row.attr( 'status' ) !== val.status ) {
				$row.html( '' );
				video2commons.setupTaskRow( $row, id, val.status );
			}

			var $title = $row.find( '#' + id + '-title' );
			if ( $title.text() !== val.title ) {
				$title.text( val.title );
			}

			var $hostname = $row.find( '#' + id + '-hostname' );
			if ( $hostname.text() !== val.hostname ) {
				$hostname.text( val.hostname ?? 'N/A' );
			}

			var setStatusText = function ( htmlortext, href, text ) {
				var $e = $row.find( '#' + id + '-statustext' );
				if ( !href ) {
					if ( $e.text() !== htmlortext ) {
						$e.text( htmlortext );
					}
				} else {
					var link = $e.html( htmlortext )
						.find( 'a' )
						.attr( 'href', href );
					if ( text ) {
						link.text( text );
					}
				}
			};
			if ( val.status === 'done' ) {
				setStatusText(
					nunjucksEnv.getFilter( 'process_link' )( i18n.taskDone ).toString(),
					val.url.replace( '%3A', ':' ), // Ugly HACK for v2c issue #92
					val.text
				);
			} else if ( val.status === 'needssu' ) {
				setStatusText(
					nunjucksEnv.getFilter( 'process_link' )( i18n.errorTooLarge ).toString(),
					video2commons.makeSSULink( [ val ] )
				);
			} else if ( val.status === 'fail' ) {
				setStatusText( val.text, val.url, val.url );
				if ( val.restartable ) {
					$row.find( '#' + id + '-restartbutton' )
						.show()
						.off()
						.click( function () {
							video2commons.eventTask( this, 'restart' );
						} );
				} else {
					$row.find( '#' + id + '-restartbutton' )
						.off()
						.hide();
				}
			} else {
				setStatusText( val.text );
			}

			if ( val.status === 'progress' ) {
				video2commons.setProgressBar( $row.find( '#' + id + '-progress' ), val.progress );
			}

			if ( val.status === 'needssu' ) {
				SSUs[ val.id ] = val;
			} else {
				delete SSUs[ val.id ];
			}
		},

		setupTaskRow: function ( $row, id, status ) {
			switch ( status ) {
				case 'progress':
					/* eslint-disable indent */
					$row.append( $( '<td />' )
							.attr( 'id', id + '-title' ) )
						.append( $( '<td />' )
							.attr( 'id', id + '-hostname' ) )
						.append( $( '<td />' )
							.attr( 'id', id + '-status' )
							.append( $( '<span />' )
								.attr( 'id', id + '-statustext' ) ) )
						.append( $( '<td />' )
							.attr( 'id', id + '-progress' ) );
					/* eslint-enable indent */
					var $abortbutton = video2commons.eventButton( id, 'abort' );
					$row.find( '#' + id + '-status' )
						.append( $abortbutton );
					var progressbar = $row.find( '#' + id + '-progress' )
						.html( htmlContent.progressbar );
					video2commons.setProgressBar( progressbar, -1 );
					$row.removeClass( 'success danger' );
					break;
				case 'done':
					video2commons.appendButtons(
						[ video2commons.eventButton( id, 'remove' ) ],
						$row, [ 'danger', 'success' ],
						id
					);
					break;
				case 'fail':
					var $removebutton = video2commons.eventButton( id, 'remove' );
					var $restartbutton = video2commons.eventButton( id, 'restart' )
						.hide();

					video2commons.appendButtons(
						[ $removebutton, $restartbutton ],
						$row, [ 'success', 'danger' ],
						id
					);
					break;
				case 'needssu':
					video2commons.appendButtons(
						[ video2commons.eventButton( id, 'remove' ) ],
						$row, [ 'success', 'danger' ],
						id
					);
					break;
				case 'abort':
					video2commons.appendButtons(
						[],
						$row, [ 'success', 'danger' ],
						id
					);
					break;
			}

			$row.attr( 'status', status );
		},

		makeSSULink: function ( vals ) {
			var urls = $.map( vals, function ( val /* , key */ ) {
					return '* ' + val.url;
				} ).join( '\n' ),
				checksums = $.map( vals, function ( val /* , key */ ) {
					return '| ' + val.filename + ' | ' + val.hashsum + ' |';
				} ).join( '\n' );
			return 'https://phabricator.wikimedia.org/maniphest/task/edit/form/106/?' + $.param( {
				title: 'Server side upload for ' + username,
				projects: 'video2commons,server-side-upload-request',
				description: ssuTemplate.replace( '{{{ urls }}}', urls ).replace( '{{{ checksums }}}', checksums )
			} );
		},

		setProgressBar: function ( $item, progress ) {
			var $bar = $item.find( '.progress-bar' );
			if ( progress < 0 ) {
				$bar.addClass( 'progress-bar-striped active' )
					.addClass( 'active' )
					.text( '' );
				progress = 100;
			} else {
				$bar.removeClass( 'progress-bar-striped active' )
					.text( Math.round( progress ) + '%' );
			}

			$bar.attr( {
				'aria-valuenow': progress,
				'aria-valuemin': '0',
				'aria-valuemax': '100',
				style: 'width:' + progress + '%'
			} );
		},

		getTaskIDFromDOMID: function ( id ) {
			var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|abortbutton|removebutton|restartbutton))?$/.exec( id );
			return result[ 1 ];
		},

		eventTask: function ( obj, eventName ) {
			var $obj = $( obj );
			if ( $obj.is( '.disabled' ) ) {
				return;
			}
			$obj.off()
				.addClass( 'disabled' );

			video2commons.apiPost( 'task/' + eventName, {
				id: video2commons.getTaskIDFromDOMID( $obj.attr( 'id' ) )
			} )
				.done( function ( data ) {
					if ( data.error ) {
						// eslint-disable-next-line no-alert
						window.alert( data.error );
					}
					video2commons.checkStatus();
				} );
		},

		setText: function ( arr, data ) {
			for ( var i = 0; i < arr.length; i++ ) {
				$addTaskDialog.find( '#' + arr[ i ] )
					.text( data[ arr[ i ] ] );
			}
		},

		eventButton: function ( id, eventName ) {
			return $( htmlContent[ eventName + 'button' ] )
				.attr( 'id', id + '-' + eventName + 'button' )
				.off()
				.click( function () {
					video2commons.eventTask( this, eventName );
				} );
		},

		appendButtons: function ( buttonArray, $row, type, id ) {
			$row.append( $( '<td />' )
				.attr( 'id', id + '-title' ) );

			var $buttons = $( '<td />' )
				.attr( 'id', id + '-status' )
				.attr( 'colspan', '3' )
				.append( $( '<span />' )
					.attr( 'id', id + '-statustext' ) );

			if ( buttonArray.length ) {
				$buttons.append( buttonArray[ 0 ] );
			}

			for ( var i = 1; i < buttonArray.length; i++ ) {
				$buttons.append( buttonArray[ i ] );
			}

			$row.append( $buttons )
				.removeClass( type[ 0 ] )
				.addClass( type[ 1 ] );
		},

		// Functions related to adding new tasks
		addTask: function ( taskdata ) {
			if ( !$addTaskDialog ) {
				$addTaskDialog = $( '<div>' )
					.html( nunjucksEnv.render( 'addTask.html' ) );

				$addTaskDialog.addClass( 'modal fade' )
					.attr( {
						id: 'addTaskDialog',
						role: 'dialog'
					} );
				$( 'body' )
					.append( $addTaskDialog );

				$addTaskDialog.find( '#btn-prev' )
					.html( htmlContent.prevbutton );
				$addTaskDialog.find( '#btn-next' )
					.html( htmlContent.nextbutton );

				$addTaskDialog.find( '#btn-cancel' )
					.click( function () {
						video2commons.abortUpload();
					} );

				// HACK
				$addTaskDialog.find( '.modal-body' )
					.keypress( function ( e ) {
						if ( ( e.which || e.keyCode ) === 13 &&
							!( $( ':focus' )
								.is( 'textarea' ) ) ) {
							$addTaskDialog.find( '.modal-footer #btn-next' )
								.click();
							e.preventDefault();
						}
					} );

			}

			video2commons.openTaskModal( taskdata );
		},

		openTaskModal: function ( taskdata ) {
			$addTaskDialog.find( '#dialog-spinner' )
				.hide();
			$addTaskDialog.find( '.modal-body' )
				.html( '<center>' + loaderImage + '</center>' );

			video2commons.newTask( taskdata );
			$addTaskDialog.modal( {
				backdrop: 'static'
			} );

			// HACK
			$addTaskDialog.on( 'shown.bs.modal', function () {
				$addTaskDialog.find( '#url' )
					.focus();
			} );

			video2commons.reactivatePrevNextButtons();
		},

		newTask: function ( taskdata ) {
			newTaskData = {
				step: 'source',
				url: '',
				date: '',
				extractor: '',
				audio: true,
				video: true,
				subtitles: true,
				filename: true,
				formats: [],
				format: '',
				filedesc: '',
				dateCategory: '',
				uploadedFile: {},
				initialUrlValidated: false,
				initialFilenameValidated: false,
				initialFiledescValidated: false,
				nextStep: 'source',
				history: [],
				videos: [],
				selectedVideos: [],
				editingVideoIndex: null,
			};
			$.extend( newTaskData, taskdata );

			video2commons.setupAddTaskDialog();
		},

		setupAddTaskDialog: function () {
			switch ( newTaskData.step ) {
				case 'source':
					$addTaskDialog.find( '.modal-body' )
						.html( nunjucksEnv.render( 'sourceForm.html' ) );

					$addTaskDialog.find( 'a#fl' )
						.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Acceptable_licenses' );
					$addTaskDialog.find( 'a#pd' )
						.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Material_in_the_public_domain' );
					$addTaskDialog.find( 'a#fu' )
						.attr( 'href', '//commons.wikimedia.org/wiki/Commons:FU' );

					$addTaskDialog.find( '#url' )
						.val( newTaskData.url )
						.on( 'input', function () {
							if ( newTaskData.url !== $( this ).val() ) {
								newTaskData.url = $( this ).val();
							}

							const youtubeRegex = /(https?:\/\/)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)\/(watch\?.*?(?=v=)v=|embed\/|v\/|.+\?v=)?([^&=%\?]{11})/;
							if ( newTaskData.url.match( youtubeRegex ) ) {
								$addTaskDialog.find( '#youtube-warning' )
									.removeClass( 'hidden' );
							} else {
								$addTaskDialog.find( '#youtube-warning' )
									.addClass( 'hidden' );
							}
						} )
						.focus();
					$addTaskDialog.find( '#video' )
						.prop( 'checked', newTaskData.video );
					$addTaskDialog.find( '#audio' )
						.prop( 'checked', newTaskData.audio );
					$addTaskDialog.find( '#subtitles' )
						.prop( 'checked', newTaskData.subtitles );

					video2commons.initUpload();
					break;
				case 'playlist':
					$addTaskDialog.find( '.modal-body' )
						.html( nunjucksEnv.render( 'playlistForm.html', { task: newTaskData } ) );

					$addTaskDialog.find( '.video-select' ).each( ( i, el ) => {
						const video = newTaskData.videos[ i ];
						if ( newTaskData.selectedVideos.indexOf( video ) >= 0 ) {
							$( el ).prop( 'checked', true );
						}
					} );

					const allChecked = $addTaskDialog.find( '.video-select:checked' ).length === $addTaskDialog.find( '.video-select' ).length;
					$addTaskDialog.find( '#select-all' ).prop( 'checked', allChecked );

					$addTaskDialog.find( '#select-all' )
						.off()
						.change( function () {
							const isChecked = $( this ).is( ':checked' );
							$addTaskDialog.find( '.video-select' ).prop( 'checked', isChecked );
						} );

					$addTaskDialog.find( '.video-select' )
						.off()
						.change( function () {
							const allChecked = $addTaskDialog.find( '.video-select:checked' ).length === $addTaskDialog.find( '.video-select' ).length;
							$addTaskDialog.find( '#select-all' ).prop( 'checked', allChecked );
						} );

					$addTaskDialog.find( '.btn-edit' )
						.off()
						.click( function () {
							const videoIndex = $( this ).data( 'video-index' );

							newTaskData.selectedVideos = form.getPlaylistData();
							newTaskData.editingVideoIndex = videoIndex;
							newTaskData.history.push( newTaskData.step );
							newTaskData.step = 'target';
							video2commons.setupAddTaskDialog();
							video2commons.reactivatePrevNextButtons();
						} );
					break;
				case 'target':
					const source = newTaskData.type === 'playlist'
						? newTaskData.videos[ newTaskData.editingVideoIndex ]
						: newTaskData;

					$addTaskDialog.find( '.modal-body' )
						.html( nunjucksEnv.render( 'targetForm.html' ) );

					$addTaskDialog.find( '#filename' )
						.val( source.filename.trim() )
						.focus();
					$.each( newTaskData.formats, function ( i, desc ) {
						$addTaskDialog.find( '#format' )
							.append( $( '<option></option>' )
								.text( desc ) );
					} );
					$addTaskDialog.find( '#format' )
						.val( source.format );
					$addTaskDialog.find( '#filedesc' )
						.val( source.filedesc );

					$addTaskDialog.find( '#dateCategory' )
						.attr( 'placeholder', getDateCategoryPlaceholder( source ) )
						.val( source.dateCategory || '' );

					const dateCategoryOptions = getDateCategoryOptions( source );
					$.each( dateCategoryOptions, function ( _, option ) {
						$addTaskDialog.find( '#dateCategoryOptions' )
							.append( $( '<option></option>' ).val( option ) );
					} );

					// Add validation feedback for the date category whenever
					// the input value in the box changes.
					$addTaskDialog.find( '#dateCategory' ).on( 'input', function () {
						const result = validateDateCategory( $( this ).val().trim() );
						if ( result.valid ) {
							$addTaskDialog.find( '#dateCategoryError' ).hide();
							$addTaskDialog.find( '#dateCategory-group' ).removeClass( 'has-error' );
						} else {
							$addTaskDialog.find( '#dateCategoryError' ).text( result.error ).show();
							$addTaskDialog.find( '#dateCategory-group' ).addClass( 'has-error' );
						}
					} );
					break;
				case 'confirm':
					const confirmForm = newTaskData.type === 'playlist'
						? nunjucksEnv.render( 'playlistConfirmForm.html', { task: newTaskData } )
						: nunjucksEnv.render( 'confirmForm.html' );
					$addTaskDialog.find( '.modal-body' ).html( confirmForm );

					var keep = [];
					if ( newTaskData.video ) {
						keep.push( i18n.video );
					}
					if ( newTaskData.audio ) {
						keep.push( i18n.audio );
					}
					if ( newTaskData.subtitles ) {
						keep.push( i18n.subtitles );
					}
					$addTaskDialog.find( '#keep' )
						.text( keep.join( ', ' ) );

					video2commons.setText( [
						'url',
						'extractor',
						'filename',
						'format'
					], newTaskData );

					$addTaskDialog.find( '#filedesc' )
						.val( newTaskData.filedesc );

					$addTaskDialog.find( '#btn-next' )
						.focus();
			}
		},

		reactivatePrevNextButtons: function () {
			$addTaskDialog.find( '#dialog-spinner' )
				.hide();
			switch ( newTaskData.step ) {
				case 'source':
					$addTaskDialog.find( '#btn-prev' )
						.addClass( 'disabled' )
						.off();

					$addTaskDialog.find( '#btn-next' )
						.html( htmlContent.nextbutton );
					video2commons.setPrevNextButton( 'next' );
					break;
				case 'playlist':
					video2commons.setPrevNextButton( 'prev' );

					$addTaskDialog.find( '#btn-next' )
						.html( htmlContent.nextbutton );
					video2commons.setPrevNextButton( 'next' );
					break;
				case 'target':
					video2commons.setPrevNextButton( 'prev' );

					if ( newTaskData.type === 'playlist' ) {
						$addTaskDialog.find( '#btn-next' )
							.html( htmlContent.confirmbutton );
					} else {
						$addTaskDialog.find( '#btn-next' )
							.html( htmlContent.nextbutton );
					}
					video2commons.setPrevNextButton( 'next' );
					break;
				case 'confirm':
					video2commons.setPrevNextButton( 'prev' );

					$addTaskDialog.find( '#btn-next' )
						.removeClass( 'disabled' )
						.html( htmlContent.confirmbutton )
						.off()
						.click( function () {
							video2commons.disablePrevNext( false );

							$addTaskDialog.modal( 'hide' );
							$( '#tasktable > tbody' )
								.append( '<tr id="task-new"><td colspan="3">' + loaderImage + '</td></tr>' );
							window.scrollTo( 0, document.body.scrollHeight );

							newTaskData.uploadedFile = {}; // FIXME

							let tasks = [];

							if ( newTaskData.type === 'playlist' ) {
								tasks = newTaskData.selectedVideos.map( ( video ) => {
									let filedesc = video.filedesc;
									if ( video.dateCategory ) {
										filedesc += '\n[[Category:' + video.dateCategory + ']]';
									}

									return {
										url: video.url,
										extractor: video.extractor,
										subtitles: newTaskData.subtitles,
										filename: video.filename,
										filedesc: filedesc,
										format: video.format,
									};
								} );
							} else {
								let filedesc = newTaskData.filedesc;
								if ( newTaskData.dateCategory ) {
									filedesc += '\n[[Category:' + newTaskData.dateCategory + ']]';
								}

								tasks.push( {
									url: newTaskData.url,
									extractor: newTaskData.extractor,
									subtitles: newTaskData.subtitles,
									filename: newTaskData.filename,
									filedesc: filedesc,
									format: newTaskData.format,
								} );
							}

							// Run all of the tasks in parallel. Only check for
							// the status after all of theme have been queued.
							video2commons.runWithConcurrency(
								tasks.map( ( task ) => () =>
									api.startTask( task ).done( ( data ) => {
										if ( data.error ) {
											// eslint-disable-next-line no-alert
											window.alert( data.error );
										}
									} )
								)
							).always( () => {
								video2commons.checkStatus();
							} );
						} );
			}
		},

		setPrevNextButton: function ( button ) {
			$addTaskDialog.find( '#btn-' + button )
				.removeClass( 'disabled' )
				.off()
				.click( function () {
					video2commons.processInput( button );
				} );
		},

		disablePrevNext: function ( spin ) {
			$addTaskDialog.find( '.modal-body #dialog-errorbox' )
				.hide();
			$addTaskDialog.find( '#btn-prev' )
				.addClass( 'disabled' )
				.off();
			$addTaskDialog.find( '#btn-next' )
				.addClass( 'disabled' )
				.off();
			if ( spin ) {
				$addTaskDialog.find( '#dialog-spinner' )
					.show();
			}
		},

		processInput: function ( button ) {
			const currentStep = newTaskData.step;

			const step = steps[ currentStep ];
			if ( !step ) {
				console.error( 'Unknown step:', currentStep );
				return;
			}

			if ( button === 'next' ) {
				const validationPromise = step();
				video2commons.promiseWorkingOn(
					validationPromise.done( function () {
						video2commons.transitionStep( button );
					} )
				);
			} else {
				video2commons.transitionStep( button );
				video2commons.reactivatePrevNextButtons();
			}
		},

		transitionStep: function ( button ) {
			if ( button === 'prev' && newTaskData.history.length > 0 ) {
				newTaskData.step = newTaskData.history.pop();
				video2commons.setupAddTaskDialog();
			} else if ( button === 'next' ) {
				const lastStep = newTaskData.history[ newTaskData.history.length - 1 ];

				if ( newTaskData.nextStep === lastStep ) {
					newTaskData.step = newTaskData.history.pop();
				} else {
					newTaskData.history.push( newTaskData.step );
					newTaskData.step = newTaskData.nextStep;
				}

				video2commons.setupAddTaskDialog();
			}
		},

		promiseWorkingOn: function ( promise ) {
			video2commons.disablePrevNext( true );

			return promise
				.fail( function ( error ) {
					if ( !$addTaskDialog.find( '.modal-body #dialog-errorbox' )
						.length ) {
						$addTaskDialog.find( '.modal-body' )
							.append(
								$( '<div class="alert alert-danger" id="dialog-errorbox"></div>' )
							);
					}
					$addTaskDialog.find( '.modal-body #dialog-errorbox' )
						.text( 'Error: ' + error )
						.show();
				} )
				.always( video2commons.reactivatePrevNextButtons );
		},

		abortUpload: function ( deferred, abortReason ) {
			if ( deferred && deferred.state() === 'pending' ) {
				deferred.reject( abortReason );
			}
			if ( window.jqXHR && window.jqXHR.abort ) {
				window.jqXHR.abort();
			}
		},

		initUpload: function () {
			var deferred;

			window.jqXHR = $addTaskDialog.find( '#fileupload' ).fileupload( {
				dataType: 'json',
				formData: {
					// eslint-disable-next-line no-underscore-dangle,camelcase
					_csrf_token: csrfToken
				},
				maxChunkSize: 4 << 20, // eslint-disable-line no-bitwise
				sequentialUploads: true
			} )
				.on( 'fileuploadadd', function ( e, data ) {
					window.jqXHR = data.submit();
					deferred = $.Deferred();
					video2commons.promiseWorkingOn( deferred.promise() );
					$addTaskDialog.find( '#src-url' ).hide();
					$addTaskDialog.find( '#src-uploading' ).show();

					$addTaskDialog.find( '#upload-abort' )
						.off()
						.click( function () {
							video2commons.abortUpload( deferred, 'Upload aborted.' );
						} );
				} )
				.on( 'fileuploadchunkdone', function ( e, data ) {
					if ( data.result.filekey ) {
						data.formData.filekey = data.result.filekey;
					}
					if ( data.result.result === 'Continue' ) {
						if ( data.result.offset !== data.uploadedBytes ) {
							video2commons.abortUpload( deferred, 'Unexpected offset! Expected: ' + data.uploadedBytes + ' Returned: ' + data.result.offset );
							// data.uploadedBytes = data.result.offset; // FIXME: Doesn't work, so we have to abort it
						}
					} else if ( data.result.error ) {
						video2commons.abortUpload( deferred, data.result.error );
					} else {
						video2commons.abortUpload();
					}
				} )
				.on( 'fileuploadprogressall', function ( e, data ) {
					video2commons.setProgressBar(
						$addTaskDialog.find( '#upload-progress' ),
						data.loaded / data.total * 100
					);
				} )
				.on( 'fileuploadalways', function ( e, data ) {
					delete data.formData.filekey; // Reset
					video2commons.reactivatePrevNextButtons();
					$addTaskDialog.find( '#src-url' ).show();
					$addTaskDialog.find( '#src-uploading' ).hide();
				} )
				.on( 'fileuploadfail', function () {
					video2commons.abortUpload( deferred, 'Something went wrong while uploading... try again?' );
				} )
				.on( 'fileuploaddone', function ( e, data ) {
					if ( data.result.result === 'Success' ) {
						var url = 'uploads:' + data.result.filekey;
						newTaskData.uploadedFile[ url ] = data.files[ 0 ];
						$addTaskDialog.find( '#url' )
							.val( url );
						deferred.resolve();
					} else {
						video2commons.abortUpload( deferred, 'Upload does not seem to be successful.' );
					}
				} );
		},

		askAPI: function ( url, datain, dataout, object=null ) {
			if ( object == null ) {
				object = newTaskData;
			}

			var deferred = $.Deferred();
			video2commons.apiPost( url, datain )
				.done( function ( data ) {
					if ( data.error ) {
						deferred.reject( data.error );
						return;
					}
					for ( var i = 0; i < dataout.length; i++ ) {
						var name = dataout[ i ];
						if ( newTaskDataQS && newTaskDataQS[ name ] ) {
							object[ name ] = newTaskDataQS[ name ];
						} else if ( data[ name ] ) {
							object[ name ] = data[ name ];
						}
					}

					deferred.resolve( data );
				} )
				.fail( function () {
					deferred.reject( 'Something weird happened. Please try again.' );
				} );

			return deferred.promise();
		},

		apiPost: function ( endpoint, data ) {
			// eslint-disable-next-line no-underscore-dangle,camelcase
			data._csrf_token = csrfToken;
			return $.post( 'api/' + endpoint, data );
		},

		/**
		 * Run a list of tasks concurrently with a limit.
		 *
		 * @param {Array} tasks The tasks to run.
		 * @param {number} limit The maximum number of tasks to run concurrently.
		 * @return {jqery.Deferred} Will resolve when all tasks have completed.
		 */
		runWithConcurrency( tasks, limit=5 ) {
			const _tasks = tasks.slice();

			const deferred = $.Deferred();
			const results = [];

			let running = 0;
			let index = 0;

			const startTasks = () => {
				if ( index >= _tasks.length && running === 0 ) {
					deferred.resolve( results );
					return;
				}

				// Start new tasks up to the limit.
				while ( running < limit && index < _tasks.length ) {
					const currentIndex = index++;
					const task = _tasks[ currentIndex ];
					running++;

					task().then( ( result ) => {
						results[ currentIndex ] = result;
					} ).fail( ( error ) => {
						results[ currentIndex ] = { error };
					} ).always( () => {
						running--;
						startTasks();
					} );
				}
			};

			startTasks();
			return deferred.promise();
		}
	};

	$( document )
		.ready( function () {
			video2commons.init();
		} );
}( jQuery ) );
