( function( $ ) {
	'use strict';

	var i18n = window.i18n;

	var loaderImage = '<img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">';

	var rtl = i18n[ '@dir' ] === 'rtl';
	var htmlContent = {
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
	};

	var csrf_token = '';

	i18n.a = function() {
		return function( text, render ) {
			if ( text[ 0 ] === '#' ) {
				var splitloc = text.indexOf( '|' );
				if ( splitloc < 0 ) {
					// XSS prevention: Nasty attribute escaping -- allow alphanumerics and hyphens only here
					if ( /^[a-z0-9\-]+$/i.test( text.slice( 1 ) ) )
						return '<a id="' + text.slice( 1 ) + '"></a>';
				} else {
					if ( /^[a-z0-9\-]+$/i.test( text.substring( 1, splitloc ) ) )
						return '<a id="' + text.substring( 1, splitloc ) + '">' + render( text.slice( splitloc + 1 ) ) + '</a>';
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
					csrf_token = data.csrf;
				} );
		},

		checkStatus: function() {
			if ( window.lastStatusCheck )
				clearTimeout( window.lastStatusCheck );
			var url = 'api/status';
			$.get( url )
				.done( function( data ) {
					if ( !$( '#tasktable' )
						.length ) video2commons.setupTables();
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
				"aria-valuenow": progress,
				"aria-valuemin": "0",
				"aria-valuemax": "100",
				style: "width:" + progress + "%"
			} );
		},

		getTaskIDFromDOMID: function( id ) {
			var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|abortbutton|removebutton|restartbutton))?$/.exec( id );
			return result[ 1 ];
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
						if ( text )
							link.text( text );
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

			if ( isatbottom )
				window.scrollTo( 0, document.body.scrollHeight );
		},

		addTask: function() {
			if ( !addTaskDialog ) {
				//addTask.html
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

			} else // It's not redundant because Ajax load
				video2commons.openTaskModal();
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
				filenamechecked: false,
				formats: [],
				format: '',
				filedesc: ''
			};
			video2commons.setupAddTaskDialog();
		},

		setupAddTaskDialog: function() {
			switch ( newTaskData.step ) {
				case 'source':
					//sourceForm.html
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
						} );
					break;
				case 'target':
					//targetForm.html
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
					//confirmForm.html
					$.get( 'static/html/confirmForm.min.html' )
						.success( function( dataHtml ) {
							dataHtml = Mustache.render( dataHtml, i18n );
							addTaskDialog.find( '.modal-body' )
								.html( dataHtml );

							var keep = [];
							if ( newTaskData.video ) keep.push( i18n.video );
							if ( newTaskData.audio ) keep.push( i18n.audio );
							if ( newTaskData.subtitles ) keep.push( i18n.subtitles );
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
			video2commons.reactivatePrevNextButtons();
		},

		showFormError: function( error ) {
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

			video2commons.reactivatePrevNextButtons();
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

							addTaskDialog.modal( "hide" );
							$( '#tasktable > tbody' )
								.append( '<tr id="task-new"><td colspan="3">' + loaderImage + '</td></tr>' );
							window.scrollTo( 0, document.body.scrollHeight );

							video2commons.apiPost( 'task/run', newTaskData )
								.done( function( data ) {
									if ( data.error )
										window.alert( data.error );
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
					video2commons.disablePrevNext( true );
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
			if ( spin )
				addTaskDialog.find( '#dialog-spinner' )
				.show();
		},

		processInput: function( button ) {
			var nextStep = function() {
				var action = {
					'prev': -1,
					'next': 1
				}[ button ];
				var steps = [ 'source', 'target', 'confirm' ];
				newTaskData.step = steps[ steps.indexOf( newTaskData.step ) + action ];
				video2commons.setupAddTaskDialog();
			};

			switch ( newTaskData.step ) {
				case 'source':
					var url = addTaskDialog.find( '#url' )
						.val(),
						video = addTaskDialog.find( '#video' )
						.is( ":checked" ),
						audio = addTaskDialog.find( '#audio' )
						.is( ":checked" );
					newTaskData.subtitles = addTaskDialog.find( '#subtitles' )
						.is( ":checked" );

					if ( !url ) {
						video2commons.showFormError( 'URL cannot be empty!' );
						return;
					}

					var ask2 = function() {
						if ( !newTaskData.formats.length || video !== newTaskData.video || audio !== newTaskData.audio ) {
							video2commons.askAPI( 'listformats', {
								video: video,
								audio: audio
							}, [ 'video', 'audio', 'format', 'formats' ], nextStep );
						} else {
							nextStep();
						}
					};

					var ask1 = function() {
						if ( url !== newTaskData.url ) {
							newTaskData.filenamechecked = false;
							video2commons.askAPI( 'extracturl', {
								url: url
							}, [ 'url', 'extractor', 'filedesc', 'filename' ], ask2 );
						} else {
							ask2();
						}
					};

					ask1();
					break;
				case 'target':
					var filename = addTaskDialog.find( '#filename' )
						.val();
					newTaskData.filedesc = addTaskDialog.find( '#filedesc' )
						.val();
					newTaskData.format = addTaskDialog.find( '#format' )
						.val();

					if ( !filename || !newTaskData.filedesc ) {
						video2commons.showFormError( 'Filename and file description cannot be empty!' );
						return;
					}

					if ( !newTaskData.filenamechecked || filename !== newTaskData.filename ) {
						video2commons.askAPI( 'validatefilename', {
							filename: filename
						}, [ 'filename' ], function() {
							newTaskData.filenamechecked = true;
							nextStep();
						} );
					} else {
						nextStep();
					}
					break;
				case 'confirm':
					// nothing to do in confirm screen
					nextStep();
			}
		},


		askAPI: function( url, datain, dataout, cb ) {
			video2commons.apiPost( url, datain )
				.done( function( data ) {
					if ( data.error ) {
						video2commons.showFormError( data.error );
						return;
					}
					for ( var i = 0; i < dataout.length; i++ )
						newTaskData[ dataout[ i ] ] = data[ dataout[ i ] ];
					if ( cb )
						return cb();
				} )
				.fail( function() {
					video2commons.showFormError( 'Something weird happened. Please try again.' );
				} );
		},

		eventTask: function( obj, eventName ) {
			obj = $( obj );
			if ( obj.is( '.disabled' ) ) return;
			obj.off()
				.addClass( 'disabled' );

			video2commons.apiPost( 'task/' + eventName, {
					id: video2commons.getTaskIDFromDOMID( obj.attr( 'id' ) )
				} )
				.done( function( data ) {
					if ( data.error )
						window.alert( data.error );
					video2commons.checkStatus();
				} );
		},

		setText: function( arr, data ) {
			for ( var i = 0; i < arr.length; i++ )
				addTaskDialog.find( '#' + arr[ i ] )
				.text( data[ arr[ i ] ] );
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

			if ( buttonArray.length )
				buttons.append( buttonArray[ 0 ] );

			for ( var i = 1; i < buttonArray.length; i++ )
				buttons.append( buttonArray[ i ] );

			row.append( buttons )
				.removeClass( type[ 0 ] )
				.addClass( type[ 1 ] );
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
		},

		apiPost: function( endpoint, data ) {
			data._csrf_token = csrf_token;
			return $.post( 'api/' + endpoint, data );
		}
	};

	$( document )
		.ready( function() {
			video2commons.init();
		} );
}( jQuery ) );
