( function( $ ) {
	'use strict';

	var i18n = window.i18n,
		loaderImage = '<img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">',
		rtl = i18n[ '@dir' ] === 'rtl',
		htmlContent = {
			abortbutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right"><span class="glyphicon glyphicon-remove"></span> ' + Mustache.escape( i18n.abort ) + '</button>',
			removebutton: '<button type="button" class="btn btn-danger btn-xs flip pull-right"><span class="glyphicon glyphicon-trash"></span> ' + Mustache.escape( i18n.remove ) + '</button>',
			restartbutton: '<button type="button" class="btn btn-warning btn-xs flip pull-right"><span class="glyphicon glyphicon-repeat"></span> ' + Mustache.escape( i18n.restart ) + '</button>',
			loading: '<center>' + loaderImage + '&nbsp;&nbsp;' + Mustache.escape( i18n.loading ) + '</center>',
			errorDisconnect: '<div class="alert alert-danger">' + Mustache.escape( i18n.errorDisconnect ) + '</div>',
			yourTasks: '<h4>' + Mustache.escape( i18n.yourTasks ) + '</h4><table id="tasktable" class="table"><tbody></tbody></table>',
			addTask: '<input class="btn btn-primary btn-success btn-md" type="button" accesskey="n" value="' + Mustache.escape( i18n.addTask ) + '">',
			requestServerSide: '<a class="btn btn-primary btn-success btn-md flip pull-right disabled" id="ssubtn">' + Mustache.escape( i18n.createServerSide ) + '</a>',
			progressbar: '<div class="progress"><div class="progress-bar" role="progressbar"></div></div>',
			prevbutton: '<span class="glyphicon glyphicon-chevron-' + ( rtl ? 'right' : 'left' ) + '"></span> ' + Mustache.escape( i18n.back ),
			nextbutton: Mustache.escape( i18n.next ) + ' <span class="glyphicon glyphicon-chevron-' + ( rtl ? 'left' : 'right' ) + '"></span>',
			confirmbutton: Mustache.escape( i18n.confirm ) + ' <span class="glyphicon glyphicon-ok"></span>'
		},
		csrfToken = '';

	i18n.a = function() {
		return function( text, render ) {
			if ( text[ 0 ] === '#' ) {
				var splitloc = text.indexOf( '|' );
				if ( splitloc < 0 ) {
					// XSS prevention: Nasty attribute escaping -- allow alphanumerics and hyphens only here
					if ( /^[a-z0-9\-]+$/i.test( text.slice( 1 ) ) ) {
						return '<a id="' + text.slice( 1 ) + '"></a>';
					}
				} else {
					if ( /^[a-z0-9\-]+$/i.test( text.substring( 1, splitloc ) ) ) {
						return '<a id="' + text.substring( 1, splitloc ) + '">' + render( text.slice( splitloc + 1 ) ) + '</a>';
					}
				}
			}
			return '<a>' + render( text ) + '</a>';
		};
	};

	var addTaskDialog, newTaskData;
	var video2commons = window.video2commons = {
		init: function() {
			$( '#content' )
				.html( htmlContent.loading );
			video2commons.loadCsrf();
			video2commons.checkStatus();
		},

		loadCsrf: function() {
			$.get( 'api/csrf' )
				.done( function( data ) {
					csrfToken = data.csrf;
				} );
		},

		// Functions related to showing running/finished tasks
		checkStatus: function() {
			if ( window.lastStatusCheck ) {
				clearTimeout( window.lastStatusCheck );
			}
			var url = 'api/status';
			$.get( url )
				.done( function( data ) {
					if ( !$( '#tasktable' ).length ) {
						video2commons.setupTables();
					}
					video2commons.populateResults( data );
					window.lastStatusCheck = setTimeout( video2commons.checkStatus, ( data.hasrunning ) ? 5000 : 60000 );
				} )
				.fail( function() {
					$( '#content' )
						.html( htmlContent.errorDisconnect );
				} );
		},

		setupTables: function() {
			$( '#content' )
				.html( htmlContent.yourTasks );
			var addButton = $( htmlContent.addTask );
			$( '#content' )
				.append( addButton );
			addButton.click( function() {
				video2commons.addTask();
			} );
			var ssuButton = $( htmlContent.requestServerSide );
			$( '#content' )
				.append( ssuButton.hide() );
		},

		populateResults: function( data ) {
			var isatbottom = ( window.innerHeight + window.scrollY ) >= document.body.offsetHeight;

			var table = $( '#tasktable > tbody' );

			$( '#task-new' )
				.remove();

			// remove extras
			table.find( '> tr' )
				.each( function() {
					var row = $( this ),
						id = video2commons.getTaskIDFromDOMID( row.attr( 'id' ) );
					if ( data.ids.indexOf( id ) < 0 ) {
						row.remove();
					}
				} );

			// add & update others
			$.each( data.values, function( i, val ) {
				var id = 'task-' + val.id,
					row = $( '#' + id ),
					setup = false;
				if ( !row.length ) {
					row = $( '<tr />' );
					row.attr( {
						id: id,
						status: val.status
					} );
					table.append( row );
					setup = true;
				} else if ( row.attr( 'status' ) !== val.status ) {
					row.html( '' );
					setup = true;
				}

				if ( setup ) {
					switch ( val.status ) {
						case 'progress':
							row.append( $( '<td />' )
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
							var abortbutton = video2commons.eventButton( id, 'abort' );
							row.find( '#' + id + '-status' )
								.append( abortbutton );
							var progressbar = row.find( '#' + id + '-progress' )
								.html( htmlContent.progressbar );
							video2commons.setProgressBar( progressbar, -1 );
							row.removeClass( 'success danger' );
							break;
						case 'done':
							video2commons.appendButtons(
								[ video2commons.eventButton( id, 'remove' ) ],
								row, [ 'danger', 'success' ],
								id
							);
							break;
						case 'fail':
							var removebutton = video2commons.eventButton( id, 'remove' );
							var restartbutton = video2commons.eventButton( id, 'restart' )
								.hide();

							video2commons.appendButtons(
								[ removebutton, restartbutton ],
								row, [ 'success', 'danger' ],
								id
							);
							break;
						case 'needssu':
							video2commons.appendButtons(
								[ video2commons.eventButton( id, 'remove' ) ],
								row, [ 'success', 'danger' ],
								id
							);
							break;
						case 'abort':
							video2commons.appendButtons(
								[],
								row, [ 'success', 'danger' ],
								id
							);
							break;
					}

					row.attr( 'status', val.status );
				}

				row.find( '#' + id + '-title' )
					.text( val.title );

				var setStatusText = function( htmlortext, href, text ) {
					var e = row.find( '#' + id + '-statustext' );
					if ( !href ) {
						e.text( htmlortext );
					} else {
						var link = e.html( htmlortext )
							.find( 'a' )
							.attr( 'href', href );
						if ( text ) {
							link.text( text );
						}
					}
				};
				if ( val.status === 'done' ) {
					setStatusText( Mustache.render( '{{> taskDone}}', i18n, i18n ), val.url, val.text );
				} else if ( val.status === 'needssu' ) {
					setStatusText( Mustache.render( '{{> errorTooLarge}}', i18n, i18n ), val.url );
				} else if ( val.status === 'fail' ) {
					setStatusText( val.text );
					if ( val.restartable ) {
						row.find( '#' + id + '-restartbutton' )
							.show()
							.off()
							.click( function() {
								video2commons.eventTask( this, 'restart' );
							} );
					} else {
						row.find( '#' + id + '-restartbutton' )
							.off()
							.hide();
					}
				} else {
					setStatusText( val.text );
				}

				if ( val.status === 'progress' ) {
					video2commons.setProgressBar( row.find( '#' + id + '-progress' ), val.progress );
				}
			} );

			if ( data.ssulink ) {
				$( '#ssubtn' )
					.removeClass( 'disabled' )
					.show()
					.attr( 'href', data.ssulink );
			} else {
				$( '#ssubtn' )
					.addClass( 'disabled' )
					.hide();
			}

			if ( isatbottom ) {
				window.scrollTo( 0, document.body.scrollHeight );
			}
		},

		setProgressBar: function( item, progress ) {
			var bar = item.find( '.progress-bar' );
			if ( progress < 0 ) {
				bar.addClass( 'progress-bar-striped active' )
					.addClass( 'active' )
					.text( '' );
				progress = 100;
			} else {
				bar.removeClass( 'progress-bar-striped active' )
					.text( progress + '%' );
			}

			bar.attr( {
				'aria-valuenow': progress,
				'aria-valuemin': '0',
				'aria-valuemax': '100',
				style: 'width:' + progress + '%'
			} );
		},

		getTaskIDFromDOMID: function( id ) {
			var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|abortbutton|removebutton|restartbutton))?$/.exec( id );
			return result[ 1 ];
		},

		eventTask: function( obj, eventName ) {
			obj = $( obj );
			if ( obj.is( '.disabled' ) ) {
				return;
			}
			obj.off()
				.addClass( 'disabled' );

			video2commons.apiPost( 'task/' + eventName, {
				id: video2commons.getTaskIDFromDOMID( obj.attr( 'id' ) )
			} )
				.done( function( data ) {
					if ( data.error ) {
						window.alert( data.error );
					}
					video2commons.checkStatus();
				} );
		},

		setText: function( arr, data ) {
			for ( var i = 0; i < arr.length; i++ ) {
				addTaskDialog.find( '#' + arr[ i ] )
					.text( data[ arr[ i ] ] );
			}
		},

		eventButton: function( id, eventName ) {
			return $( htmlContent[ eventName + 'button' ] )
				.attr( 'id', id + '-' + eventName + 'button' )
				.off()
				.click( function() {
					video2commons.eventTask( this, eventName );
				} );
		},

		appendButtons: function( buttonArray, row, type, id ) {
			row.append( $( '<td />' )
				.attr( 'id', id + '-title' )
				.attr( 'width', '30%' ) );

			var buttons = $( '<td />' )
				.attr( 'id', id + '-status' )
				.attr( 'width', '70%' )
				.attr( 'colspan', '2' )
				.append( $( '<span />' )
					.attr( 'id', id + '-statustext' ) );

			if ( buttonArray.length ) {
				buttons.append( buttonArray[ 0 ] );
			}

			for ( var i = 1; i < buttonArray.length; i++ ) {
				buttons.append( buttonArray[ i ] );
			}

			row.append( buttons )
				.removeClass( type[ 0 ] )
				.addClass( type[ 1 ] );
		},

		// Functions related to adding new tasks
		addTask: function() {
			if ( !addTaskDialog ) {
				// addTask.html
				$.get( 'static/html/addTask.min.html' )
					.success( function( data ) {

						addTaskDialog = $( '<div>' )
							.html( Mustache.render( data, i18n ) );

						addTaskDialog.addClass( 'modal fade' )
							.attr( {
								id: 'addTaskDialog',
								role: 'dialog'
							} );
						$( 'body' )
							.append( addTaskDialog );

						addTaskDialog.find( '#btn-prev' )
							.html( htmlContent.prevbutton );
						addTaskDialog.find( '#btn-next' )
							.html( htmlContent.nextbutton );

						addTaskDialog.find( '#btn-cancel' )
							.click( function() {
								if ( window.jqXHR ) {
									window.jqXHR.abort();
								}
							} );

						// HACK
						addTaskDialog.find( '.modal-body' )
							.keypress( function( e ) {
								if ( ( e.which || e.keyCode ) === 13 &&
									!( $( ':focus' )
										.is( 'textarea' ) ) ) {
									addTaskDialog.find( '.modal-footer #btn-next' )
										.click();
									e.preventDefault();
								}
							} );

						video2commons.openTaskModal();
					} );

			} else { // It's not redundant because Ajax load
				video2commons.openTaskModal();
			}
		},

		openTaskModal: function() {
			addTaskDialog.find( '#dialog-spinner' )
				.hide();
			addTaskDialog.find( '.modal-body' )
				.html( '<center>' + loaderImage + '</center>' );

			video2commons.newTask();
			addTaskDialog.modal();

			// HACK
			addTaskDialog.on( 'shown.bs.modal', function() {
				addTaskDialog.find( '#url' )
					.focus();
			} );

			video2commons.reactivatePrevNextButtons();
		},

		newTask: function() {
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
				filenamechecked: false,
				filedescchecked: false
			};
			video2commons.setupAddTaskDialog();
		},

		setupAddTaskDialog: function() {
			switch ( newTaskData.step ) {
				case 'source':
					// sourceForm.html
					$.get( 'static/html/sourceForm.min.html' )
						.success( function( dataHtml ) {
							dataHtml = Mustache.render( dataHtml, i18n, i18n );
							addTaskDialog.find( '.modal-body' )
								.html( dataHtml );

							addTaskDialog.find( 'a#vc' )
								.attr( 'href', '//tools.wmflabs.org/videoconvert/' );
							addTaskDialog.find( 'a#fl' )
								.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Acceptable_licenses' );
							addTaskDialog.find( 'a#pd' )
								.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Material_in_the_public_domain' );
							addTaskDialog.find( 'a#fu' )
								.attr( 'href', '//commons.wikimedia.org/wiki/Commons:FU' );

							addTaskDialog.find( '#url' )
								.val( newTaskData.url )
								.focus();
							addTaskDialog.find( '#video' )
								.prop( 'checked', newTaskData.video );
							addTaskDialog.find( '#audio' )
								.prop( 'checked', newTaskData.audio );
							addTaskDialog.find( '#subtitles' )
								.prop( 'checked', newTaskData.subtitles );

							video2commons.initUpload();
						} );
					break;
				case 'target':
					// targetForm.html
					$.get( 'static/html/targetForm.min.html' )
						.success( function( dataHtml ) {
							dataHtml = Mustache.render( dataHtml, i18n );
							addTaskDialog.find( '.modal-body' )
								.html( dataHtml );

							addTaskDialog.find( '#filename' )
								.val( newTaskData.filename )
								.focus();
							$.each( newTaskData.formats, function( i, desc ) {
								addTaskDialog.find( '#format' )
									.append( $( '<option></option>' )
										.text( desc ) );
							} );
							addTaskDialog.find( '#format' )
								.val( newTaskData.format );
							addTaskDialog.find( '#filedesc' )
								.val( newTaskData.filedesc );
						} );
					break;
				case 'confirm':
					// confirmForm.html
					$.get( 'static/html/confirmForm.min.html' )
						.success( function( dataHtml ) {
							dataHtml = Mustache.render( dataHtml, i18n );
							addTaskDialog.find( '.modal-body' )
								.html( dataHtml );

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
							addTaskDialog.find( '#keep' )
								.text( keep.join( ', ' ) );

							video2commons.setText( [
								'url',
								'extractor',
								'filename',
								'format'
							], newTaskData );

							addTaskDialog.find( '#filedesc' )
								.val( newTaskData.filedesc );

							addTaskDialog.find( '#btn-next' )
								.focus();
						} );
			}
		},

		reactivatePrevNextButtons: function() {
			addTaskDialog.find( '#dialog-spinner' )
				.hide();
			switch ( newTaskData.step ) {
				case 'source':
					addTaskDialog.find( '#btn-prev' )
						.addClass( 'disabled' )
						.off();

					addTaskDialog.find( '#btn-next' )
						.html( htmlContent.nextbutton );
					video2commons.setPrevNextButton( 'next' );
					break;
				case 'target':
					video2commons.setPrevNextButton( 'prev' );

					addTaskDialog.find( '#btn-next' )
						.html( htmlContent.nextbutton );
					video2commons.setPrevNextButton( 'next' );
					break;
				case 'confirm':
					video2commons.setPrevNextButton( 'prev' );

					addTaskDialog.find( '#btn-next' )
						.removeClass( 'disabled' )
						.html( htmlContent.confirmbutton )
						.off()
						.click( function() {
							video2commons.disablePrevNext( false );

							addTaskDialog.modal( 'hide' );
							$( '#tasktable > tbody' )
								.append( '<tr id="task-new"><td colspan="3">' + loaderImage + '</td></tr>' );
							window.scrollTo( 0, document.body.scrollHeight );

							video2commons.apiPost( 'task/run', newTaskData )
								.done( function( data ) {
									if ( data.error ) {
										window.alert( data.error );
									}
									video2commons.checkStatus();
								} );
						} );
			}
		},

		setPrevNextButton: function( button ) {
			addTaskDialog.find( '#btn-' + button )
				.removeClass( 'disabled' )
				.off()
				.click( function() {
					video2commons.processInput( button );
				} );
		},

		disablePrevNext: function( spin ) {
			addTaskDialog.find( '.modal-body #dialog-errorbox' )
				.hide();
			addTaskDialog.find( '#btn-prev' )
				.addClass( 'disabled' )
				.off();
			addTaskDialog.find( '#btn-next' )
				.addClass( 'disabled' )
				.off();
			if ( spin ) {
				addTaskDialog.find( '#dialog-spinner' )
					.show();
			}
		},

		processInput: function( button ) {
			var resolved = $.when(); // A resolved jQuery promise

			var deferred;
			switch ( newTaskData.step ) {
				case 'source':
					deferred = $.when( ( function() {
						var video = addTaskDialog.find( '#video' ).is( ':checked' ),
							audio = addTaskDialog.find( '#audio' ).is( ':checked' );
						newTaskData.subtitles = addTaskDialog.find( '#subtitles' )
							.is( ':checked' );
						if ( !newTaskData.formats.length || video !== newTaskData.video || audio !== newTaskData.audio ) {
							return video2commons.askAPI( 'listformats', {
								video: video,
								audio: audio
							}, [ 'video', 'audio', 'format', 'formats' ] );
						} else {
							return resolved;
						}
					}() ), ( function() {
						var url = addTaskDialog.find( '#url' )
							.val();

						if ( !url ) {
							return $.Deferred()
								.reject( 'URL cannot be empty!' )
								.promise();
						}
						if ( url !== newTaskData.url ) {
							newTaskData.filenamechecked = false;
							newTaskData.filedescchecked = false;
							return video2commons.askAPI( 'extracturl', {
								url: url
							}, [ 'url', 'extractor', 'filedesc', 'filename' ] );
						} else {
							return resolved;
						}
					}() ) );
					break;
				case 'target':
					deferred = $.when( ( function() {
						var filename = addTaskDialog.find( '#filename' ).val();
						newTaskData.format = addTaskDialog.find( '#format' ).val();

						if ( !filename ) {
							return $.Deferred()
								.reject( 'Filename cannot be empty!' )
								.promise();
						}

						if ( !newTaskData.filenamechecked || filename !== newTaskData.filename ) {
							return video2commons.askAPI( 'validatefilename', {
								filename: filename
							}, [ 'filename' ] )
								.done( function() {
									newTaskData.filenamechecked = true;
								} );
						} else {
							return resolved;
						}
					}() ), ( function() {
						var filedesc = addTaskDialog.find( '#filedesc' ).val();

						if ( !filedesc ) {
							return $.Deferred()
								.reject( 'File description cannot be empty!' )
								.promise();
						}

						if ( !newTaskData.filedescchecked || filedesc !== newTaskData.filedesc ) {
							return video2commons.askAPI( 'validatefiledesc', {
								filedesc: filedesc
							}, [ 'filedesc' ] )
								.done( function() {
									newTaskData.filedescchecked = true;
								} );
						} else {
							return resolved;
						}
					}() ) );
					break;
				case 'confirm':
					// nothing to do in confirm screen
					deferred = resolved;
			}

			video2commons.promiseWorkingOn( deferred ).done( function() {
				var action = {
					prev: -1,
					next: 1
				}[ button ];
				var steps = [ 'source', 'target', 'confirm' ];
				newTaskData.step = steps[ steps.indexOf( newTaskData.step ) + action ];
				video2commons.setupAddTaskDialog();
			} );
		},

		promiseWorkingOn: function( promise ) {
			video2commons.disablePrevNext( true );

			return promise.fail( function( error ) {
				if ( !addTaskDialog.find( '.modal-body #dialog-errorbox' )
					.length ) {
					addTaskDialog.find( '.modal-body' )
						.append(
							$( '<div class="alert alert-danger" id="dialog-errorbox"></div>' )
						);
				}
				addTaskDialog.find( '.modal-body #dialog-errorbox' )
					.text( 'Error: ' + error )
					.show();
			} )
			.always( video2commons.reactivatePrevNextButtons );
		},

		initUpload: function() {
			var deferred;

			window.jqXHR = addTaskDialog.find( '#fileupload' ).fileupload( {
				dataType: 'json',
				formData: {
					_csrf_token: csrfToken // eslint-disable-line no-underscore-dangle,camelcase
				},
				maxChunkSize: 4 << 20, // eslint-disable-line no-bitwise
				sequentialUploads: true
			} )
				.on( 'fileuploadadd', function( e, data ) {
					window.jqXHR = data.submit();
					deferred = $.Deferred();
					video2commons.promiseWorkingOn( deferred.promise() );
					addTaskDialog.find( '#src-url' ).hide();
					addTaskDialog.find( '#src-uploading' ).show();
				} )
				.on( 'fileuploadchunkdone', function( e, data ) {
					if ( data.formData.filekey ) {
						data.formData.filekey = data.result.filekey;
					}
					if ( data.result.result === 'Continue' ) {
						if ( data.result.offset !== data.uploadedBytes ) {
							// console.log( 'Unexpected offset! Expected: ' + data.uploadedBytes + ' Returned: ' + data.result.offset );
							data.uploadedBytes = data.result.offset;
						}
					}
					if ( data.result.error ) {
						if ( window.jqXHR ) {
							window.jqXHR.abort();
						}
						deferred.reject( data.result.error );
					}
				} )
				.on( 'fileuploadprogress', function ( e, data ) {
					video2commons.setProgressBar(
						addTaskDialog.find( '#upload-progress' ),
						data.loaded / data.total * 100
					);
				} )
				.on( 'fileuploadalways', function() {
					video2commons.reactivatePrevNextButtons();
					addTaskDialog.find( '#src-url' ).show();
					addTaskDialog.find( '#src-uploading' ).hide();
				} )
				.on( 'fileuploadfail', function() {
					deferred.reject( 'Something went wrong while uploading... try again?' );
				} )
				.on( 'fileuploaddone', function( e, data ) {
					addTaskDialog.find( '#url' )
						.val( 'uploads:' + data.result.filekey );
					deferred.resolve();
				} );
		},

		askAPI: function( url, datain, dataout ) {
			var deferred = $.Deferred();
			video2commons.apiPost( url, datain )
				.done( function( data ) {
					if ( data.error ) {
						deferred.reject( data.error );
						return;
					}
					for ( var i = 0; i < dataout.length; i++ ) {
						newTaskData[ dataout[ i ] ] = data[ dataout[ i ] ];
					}

					deferred.resolve( data );
				} )
				.fail( function() {
					deferred.reject( 'Something weird happened. Please try again.' );
				} );

			return deferred.promise();
		},

		apiPost: function( endpoint, data ) {
			data._csrf_token = csrfToken; // eslint-disable-line no-underscore-dangle,camelcase
			return $.post( 'api/' + endpoint, data );
		}
	};

	$( document )
		.ready( function() {
			video2commons.init();
		} );
}( jQuery ) );
