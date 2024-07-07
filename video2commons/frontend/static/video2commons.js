/* globals nunjucks: false, io: false, Qs: false */
( function ( $ ) {
	'use strict';

	var config = window.config,
		i18n = window.i18n,
		loaderImage = '<img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">',
		rtl = i18n[ '@dir' ] === 'rtl',
		htmlContent = {
			abortbutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right"><span class="glyphicon glyphicon-remove"></span> ' + nunjucks.lib.escape( i18n.abort ) + '</button>',
			removebutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right"><span class="glyphicon glyphicon-trash"></span> ' + nunjucks.lib.escape( i18n.remove ) + '</button>',
			restartbutton: '<button type="button" class="btn btn-warning btn-xs flip pull-right"><span class="glyphicon glyphicon-repeat"></span> ' + nunjucks.lib.escape( i18n.restart ) + '</button>',
			loading: '<center>' + loaderImage + '&nbsp;&nbsp;' + nunjucks.lib.escape( i18n.loading ) + '</center>',
			errorDisconnect: '<div class="alert alert-danger">' + nunjucks.lib.escape( i18n.errorDisconnect ) + '</div>',
			yourTasks: '<h4>' + nunjucks.lib.escape( i18n.yourTasks ) + '</h4><table id="tasktable" class="table"><tbody></tbody></table>',
			addTask: '<input class="btn btn-primary btn-success btn-md" type="button" accesskey="n" value="' + nunjucks.lib.escape( i18n.addTask ) + '">',
			requestServerSide: '<a class="btn btn-primary btn-success btn-md flip pull-right disabled" id="ssubtn">' + nunjucks.lib.escape( i18n.createServerSide ) + '</a>',
			progressbar: '<div class="progress"><div class="progress-bar" role="progressbar"></div></div>',
			prevbutton: '<span class="glyphicon glyphicon-chevron-' + ( rtl ? 'right' : 'left' ) + '"></span> ' + nunjucks.lib.escape( i18n.back ),
			nextbutton: nunjucks.lib.escape( i18n.next ) + ' <span class="glyphicon glyphicon-chevron-' + ( rtl ? 'left' : 'right' ) + '"></span>',
			confirmbutton: nunjucks.lib.escape( i18n.confirm ) + ' <span class="glyphicon glyphicon-ok"></span>'
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
			$( '#content' )
				.html( htmlContent.yourTasks );
			var addButton = $( htmlContent.addTask );
			$( '#content' )
				.append( addButton );
			addButton.click( function () {
				video2commons.addTask();
			} );
			var ssuButton = $( htmlContent.requestServerSide );
			$( '#content' )
				.append( ssuButton.hide() );
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
				setStatusText( val.text );
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
							.attr( 'id', id + '-title' )
							.attr( 'width', '30%' ) )
						.append( $( '<td />' )
							.attr( 'id', id + '-status' )
							.attr( 'width', '40%' )
							.append( $( '<span />' )
								.attr( 'id', id + '-statustext' ) ) )
						.append( $( '<td />' )
							.attr( 'id', id + '-progress' )
							.attr( 'width', '30%' ) );
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
			return 'https://phabricator.wikimedia.org/maniphest/task/edit/form/1/?' + $.param( {
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
				.attr( 'id', id + '-title' )
				.attr( 'width', '30%' ) );

			var $buttons = $( '<td />' )
				.attr( 'id', id + '-status' )
				.attr( 'width', '70%' )
				.attr( 'colspan', '2' )
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
				extractor: '',
				audio: true,
				video: true,
				subtitles: true,
				filename: true,
				formats: [],
				format: '',
				filedesc: '',
				uploadedFile: {},
				filenamechecked: false,
				filedescchecked: false
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
						.focus();
					$addTaskDialog.find( '#video' )
						.prop( 'checked', newTaskData.video );
					$addTaskDialog.find( '#audio' )
						.prop( 'checked', newTaskData.audio );
					$addTaskDialog.find( '#subtitles' )
						.prop( 'checked', newTaskData.subtitles );

					video2commons.initUpload();
					break;
				case 'target':
					$addTaskDialog.find( '.modal-body' )
						.html( nunjucksEnv.render( 'targetForm.html' ) );

					$addTaskDialog.find( '#filename' )
						.val( newTaskData.filename )
						.focus();
					$.each( newTaskData.formats, function ( i, desc ) {
						$addTaskDialog.find( '#format' )
							.append( $( '<option></option>' )
								.text( desc ) );
					} );
					$addTaskDialog.find( '#format' )
						.val( newTaskData.format );
					$addTaskDialog.find( '#filedesc' )
						.val( newTaskData.filedesc );
					break;
				case 'confirm':
					$addTaskDialog.find( '.modal-body' )
						.html( nunjucksEnv.render( 'confirmForm.html' ) );

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
				case 'target':
					video2commons.setPrevNextButton( 'prev' );

					$addTaskDialog.find( '#btn-next' )
						.html( htmlContent.nextbutton );
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
							video2commons.apiPost( 'task/run', newTaskData )
								.done( function ( data ) {
									if ( data.error ) {
										// eslint-disable-next-line no-alert
										window.alert( data.error );
									}
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
			var resolved = $.when(); // A resolved jQuery promise

			var deferred;
			switch ( newTaskData.step ) {
				case 'source':
					deferred = $.when(
						( function () {
							var video = $addTaskDialog.find( '#video' ).is( ':checked' ),
								audio = $addTaskDialog.find( '#audio' ).is( ':checked' );
							newTaskData.subtitles = $addTaskDialog.find( '#subtitles' )
								.is( ':checked' );
							if ( !newTaskData.formats.length || video !== newTaskData.video || audio !== newTaskData.audio ) {
								return video2commons.askAPI( 'listformats', {
									video: video,
									audio: audio
								}, [ 'video', 'audio', 'format', 'formats' ] );
							} else {
								return resolved;
							}
						}() ),
						( function () {
							var url = $addTaskDialog.find( '#url' )
								.val();

							if ( !url ) {
								return $.Deferred()
									.reject( 'URL cannot be empty!' )
									.promise();
							}
							if ( !newTaskData.filename || !newTaskData.filedesc || url !== newTaskData.url ) {
								newTaskData.filenamechecked = false;
								newTaskData.filedescchecked = false;
								var uploadedFile = newTaskData.uploadedFile[ url ];
								if ( uploadedFile ) {
									newTaskData.url = url;
									return video2commons.askAPI( 'makedesc', {
										filename: uploadedFile.name || ''
									}, [ 'extractor', 'filedesc', 'filename' ] );
								} else {
									return video2commons.askAPI( 'extracturl', {
										url: url
									}, [ 'url', 'extractor', 'filedesc', 'filename' ] );
								}
							} else {
								return resolved;
							}
						}() )
					);
					break;
				case 'target':
					deferred = $.when(
						( function () {
							var filename = $addTaskDialog.find( '#filename' ).val();
							newTaskData.format = $addTaskDialog.find( '#format' ).val();

							if ( !filename ) {
								return $.Deferred()
									.reject( 'Filename cannot be empty!' )
									.promise();
							}

							if ( !newTaskData.filenamechecked || filename !== newTaskData.filename ) {
								return video2commons.askAPI( 'validatefilename', {
									filename: filename
								}, [ 'filename' ] )
									.done( function () {
										newTaskData.filenamechecked = true;
									} );
							} else {
								return resolved;
							}
						}() ),
						( function () {
							var filedesc = $addTaskDialog.find( '#filedesc' ).val();

							if ( !filedesc ) {
								return $.Deferred()
									.reject( 'File description cannot be empty!' )
									.promise();
							}

							if ( !newTaskData.filedescchecked || filedesc !== newTaskData.filedesc ) {
								return video2commons.askAPI( 'validatefiledesc', {
									filedesc: filedesc
								}, [ 'filedesc' ] )
									.done( function () {
										newTaskData.filedescchecked = true;
									} );
							} else {
								return resolved;
							}
						}() )
					);
					break;
				case 'confirm':
					// nothing to do in confirm screen
					deferred = resolved;
			}

			video2commons.promiseWorkingOn( deferred.done( function () {
				var action = {
					prev: -1,
					next: 1
				}[ button ];
				var steps = [ 'source', 'target', 'confirm' ];
				newTaskData.step = steps[ steps.indexOf( newTaskData.step ) + action ];
				video2commons.setupAddTaskDialog();
			} ) );
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

		askAPI: function ( url, datain, dataout ) {
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
							newTaskData[ name ] = newTaskDataQS[ name ];
						} else {
							newTaskData[ name ] = data[ name ];
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
		}
	};

	$( document )
		.ready( function () {
			video2commons.init();
		} );
}( jQuery ) );
