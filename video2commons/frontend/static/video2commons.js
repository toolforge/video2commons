( function( $ ) {
	'use strict';

	var i18n = window.i18n;

	var loaderImage = '<img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">';

	var htmlContent = {
		abortbutton: '<button type="button" class="btn btn-danger btn-xs pull-right"><span class="glyphicon glyphicon-remove"></span> ' + Mustache.escape( i18n.abort ) + '</button>',
		removebutton: '<button type="button" class="btn btn-danger btn-xs pull-right"><span class="glyphicon glyphicon-trash"></span> ' + Mustache.escape( i18n.remove ) + '</button>',
		restartbutton: '<button type="button" class="btn btn-warning btn-xs pull-right"><span class="glyphicon glyphicon-repeat"></span> ' + Mustache.escape( i18n.restart ) + '</button>',
		loading: '<center>' + loaderImage + '&nbsp;&nbsp;' + Mustache.escape( i18n.loading ) + '</center>',
		errorDisconnect: '<div class="alert alert-danger">' + Mustache.escape( i18n.errorDisconnect ) + '</div>',
		yourTasks: '<h4>' + Mustache.escape( i18n.yourTasks ) + '</h4><table id="tasktable" class="table"><tbody></tbody></table>',
		addTask: '<input class="btn btn-primary btn-success btn-md" type="button" accesskey="n" value="' + Mustache.escape( i18n.addTask ) + '">',
		requestServerSide: '<a class="btn btn-primary btn-success btn-md pull-right disabled" id="ssubtn">' + Mustache.escape( i18n.createServerSide ) + '</a>',
		progressbar: '<div class="progress"><div class="progress-bar" role="progressbar"></div></div>'
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

	var video2commons = window.video2commons = {};

	video2commons.init = function() {
		$( '#content' )
			.html( htmlContent.loading );
		video2commons.loadCsrf();
		video2commons.checkStatus();
	};

	video2commons.loadCsrf = function() {
		$.get( 'api/csrf' )
			.done( function( data ) {
				csrf_token = data.csrf;
			} );
	};

	video2commons.checkStatus = function() {
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
	};

	video2commons.setupTables = function() {
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
	};

	video2commons.setProgressBar = function( item, progress ) {
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
	};

	video2commons.getTaskIDFromDOMID = function( id ) {
		var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|abortbutton|removebutton|restartbutton))?$/.exec( id );
		return result[ 1 ];
	};

	video2commons.populateResults = function( data ) {
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
	};

	video2commons.addTask = function() {
		if ( !window.addTaskDialog ) {
			//addTask.html
			$.get( 'static/html/addTask.min.html' )
				.success( function( data ) {

					window.addTaskDialog = $( '<div>' )
						.html( Mustache.render( data, i18n ) );

					window.addTaskDialog.addClass( 'modal fade' )
						.attr( {
							id: 'addTaskDialog',
							role: 'dialog'
						} );
					$( 'body' )
						.append( window.addTaskDialog );

					// HACK
					window.addTaskDialog.find( '.modal-body' )
						.keypress( function( e ) {
							if ( ( e.which || e.keyCode ) === 13 &&
								!( $( ':focus' )
									.is( 'textarea' ) ) ) {
								window.addTaskDialog.find( '.modal-footer #btn-next' )
									.click();
								e.preventDefault();
							}
						} );


					video2commons.openTaskModal();

				} );

		} else // It's not redundant because Ajax load
			video2commons.openTaskModal();
	};

	video2commons.newTask = function() {
		window.newTaskData = {
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
	};

	video2commons.setupAddTaskDialog = function() {
		switch ( window.newTaskData.step ) {
			case 'source':
				//sourceForm.html
				$.get( 'static/html/sourceForm.min.html' )
					.success( function( dataHtml ) {
						dataHtml = Mustache.render( dataHtml, i18n, i18n );
						window.addTaskDialog.find( '.modal-body' )
							.html( dataHtml );

						window.addTaskDialog.find( 'a#vc' )
							.attr( 'href', '//tools.wmflabs.org/videoconvert/' );
						window.addTaskDialog.find( 'a#fl' )
							.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Acceptable_licenses' );
						window.addTaskDialog.find( 'a#pd' )
							.attr( 'href', '//commons.wikimedia.org/wiki/Commons:Licensing#Material_in_the_public_domain' );
						window.addTaskDialog.find( 'a#fu' )
							.attr( 'href', '//commons.wikimedia.org/wiki/Commons:FU' );

						window.addTaskDialog.find( '#url' )
							.val( window.newTaskData.url )
							.focus();
						window.addTaskDialog.find( '#video' )
							.prop( 'checked', window.newTaskData.video );
						window.addTaskDialog.find( '#audio' )
							.prop( 'checked', window.newTaskData.audio );
						window.addTaskDialog.find( '#subtitles' )
							.prop( 'checked', window.newTaskData.subtitles );
					} );
				break;
			case 'target':
				//targetForm.html
				$.get( 'static/html/targetForm.min.html' )
					.success( function( dataHtml ) {
						dataHtml = Mustache.render( dataHtml, i18n );
						window.addTaskDialog.find( '.modal-body' )
							.html( dataHtml );

						window.addTaskDialog.find( '#filename' )
							.val( window.newTaskData.filename )
							.focus();
						$.each( window.newTaskData.formats, function( i, desc ) {
							window.addTaskDialog.find( '#format' )
								.append( $( '<option></option>' )
									.text( desc ) );
						} );
						window.addTaskDialog.find( '#format' )
							.val( window.newTaskData.format );
						window.addTaskDialog.find( '#filedesc' )
							.val( window.newTaskData.filedesc );
					} );
				break;
			case 'confirm':
				//confirmForm.html
				$.get( 'static/html/confirmForm.min.html' )
					.success( function( dataHtml ) {
						dataHtml = Mustache.render( dataHtml, i18n );
						window.addTaskDialog.find( '.modal-body' )
							.html( dataHtml );

						var keep = [];
						if ( window.newTaskData.video ) keep.push( i18n.video );
						if ( window.newTaskData.audio ) keep.push( i18n.audio );
						if ( window.newTaskData.subtitles ) keep.push( i18n.subtitles );
						window.addTaskDialog.find( '#keep' )
							.text( keep.join( i18n.commaseperator ) );

						video2commons.setText( [
							'url',
							'extractor',
							'filename',
							'format'
						], window.newTaskData );

						window.addTaskDialog.find( '#filedesc' )
							.val( window.newTaskData.filedesc );

						window.addTaskDialog.find( '#btn-next' )
							.focus();
					} );
		}
		video2commons.reactivatePrevNextButtons();
	};

	video2commons.showFormError = function( error ) {
		if ( !window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
			.length ) {
			window.addTaskDialog.find( '.modal-body' )
				.append(
					$( '<div class="alert alert-danger" id="dialog-errorbox"></div>' )
				);
		}
		window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
			.text( 'Error: ' + error )
			.show();

		video2commons.reactivatePrevNextButtons();
	};

	video2commons.reactivatePrevNextButtons = function() {
		window.addTaskDialog.find( '#dialog-spinner' )
			.hide();
		switch ( window.newTaskData.step ) {
			case 'source':
				window.addTaskDialog.find( '#btn-prev' )
					.addClass( 'disabled' )
					.off();

				window.addTaskDialog.find( '#btn-next' )
					.html( Mustache.escape( i18n.next ) + ' <span class="glyphicon glyphicon-chevron-right"></span>' );
				video2commons.setPrevNextButton( 'next' );
				break;
			case 'target':
				video2commons.setPrevNextButton( 'prev' );

				window.addTaskDialog.find( '#btn-next' )
					.html( Mustache.escape( i18n.next ) + ' <span class="glyphicon glyphicon-chevron-right"></span>' );
				video2commons.setPrevNextButton( 'next' );
				break;
			case 'confirm':
				video2commons.setPrevNextButton( 'prev' );

				window.addTaskDialog.find( '#btn-next' )
					.removeClass( 'disabled' )
					.html( Mustache.escape( i18n.confirm ) + ' <span class="glyphicon glyphicon-ok"></span>' )
					.off()
					.click( function() {
						video2commons.disablePrevNext( false );

						window.addTaskDialog.modal( "hide" );
						$( '#tasktable > tbody' )
							.append( '<tr id="task-new"><td colspan="3">' + loaderImage + '</td></tr>' );
						window.scrollTo( 0, document.body.scrollHeight );

						video2commons.apiPost( 'task/run', window.newTaskData )
							.done( function( data ) {
								if ( data.error )
									window.alert( data.error );
								video2commons.checkStatus();
							} );
					} );
		}
	};

	video2commons.setPrevNextButton = function( button ) {
		window.addTaskDialog.find( '#btn-' + button )
			.removeClass( 'disabled' )
			.off()
			.click( function() {
				video2commons.disablePrevNext( true );
				video2commons.processInput( button );
			} );
	};

	video2commons.disablePrevNext = function( spin ) {
		window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
			.hide();
		window.addTaskDialog.find( '#btn-prev' )
			.addClass( 'disabled' )
			.off();
		window.addTaskDialog.find( '#btn-next' )
			.addClass( 'disabled' )
			.off();
		if ( spin )
			window.addTaskDialog.find( '#dialog-spinner' )
			.show();
	};

	video2commons.processInput = function( button ) {
		var nextStep = function() {
			var action = {
				'prev': -1,
				'next': 1
			}[ button ];
			var steps = [ 'source', 'target', 'confirm' ];
			window.newTaskData.step = steps[ steps.indexOf( window.newTaskData.step ) + action ];
			video2commons.setupAddTaskDialog();
		};

		switch ( window.newTaskData.step ) {
			case 'source':
				var url = window.addTaskDialog.find( '#url' )
					.val(),
					video = window.addTaskDialog.find( '#video' )
					.is( ":checked" ),
					audio = window.addTaskDialog.find( '#audio' )
					.is( ":checked" );
				window.newTaskData.subtitles = window.addTaskDialog.find( '#subtitles' )
					.is( ":checked" );

				if ( !url ) {
					video2commons.showFormError( 'URL cannot be empty!' );
					return;
				}

				var ask2 = function() {
					if ( !window.newTaskData.formats.length || video !== window.newTaskData.video || audio !== window.newTaskData.audio ) {
						video2commons.askAPI( 'listformats', {
							video: video,
							audio: audio
						}, [ 'video', 'audio', 'format', 'formats' ], nextStep );
					} else {
						nextStep();
					}
				};

				var ask1 = function() {
					if ( url !== window.newTaskData.url ) {
						window.newTaskData.filenamechecked = false;
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
				var filename = window.addTaskDialog.find( '#filename' )
					.val();
				window.newTaskData.filedesc = window.addTaskDialog.find( '#filedesc' )
					.val();
				window.newTaskData.format = window.addTaskDialog.find( '#format' )
					.val();

				if ( !filename || !window.newTaskData.filedesc ) {
					video2commons.showFormError( 'Filename and file description cannot be empty!' );
					return;
				}

				if ( !window.newTaskData.filenamechecked || filename !== window.newTaskData.filename ) {
					video2commons.askAPI( 'validatefilename', {
						filename: filename
					}, [ 'filename' ], function() {
						window.newTaskData.filenamechecked = true;
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

	};


	video2commons.askAPI = function( url, datain, dataout, cb ) {
		video2commons.apiPost( url, datain )
			.done( function( data ) {
				if ( data.error ) {
					video2commons.showFormError( data.error );
					return;
				}
				for ( var i = 0; i < dataout.length; i++ )
					window.newTaskData[ dataout[ i ] ] = data[ dataout[ i ] ];
				if ( cb )
					return cb();
			} )
			.fail( function() {
				video2commons.showFormError( 'Something weird happened. Please try again.' );
			} );
	};

	video2commons.eventTask = function( obj, eventName ) {
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
	};

	video2commons.setText = function( arr, data ) {
		for ( var i = 0; i < arr.length; i++ )
			window.addTaskDialog.find( '#' + arr[ i ] )
			.text( data[ arr[ i ] ] );
	};

	video2commons.eventButton = function( id, eventName ) {
		return $( htmlContent[ eventName + 'button' ] )
			.attr( 'id', id + '-' + eventName + 'button' )
			.off()
			.click( function() {
				video2commons.eventTask( this, eventName );
			} );
	};

	video2commons.appendButtons = function( buttonArray, row, type, id ) {
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

		//return row;
	};

	video2commons.openTaskModal = function() {
		window.addTaskDialog.find( '#dialog-spinner' )
			.hide();
		window.addTaskDialog.find( '.modal-body' )
			.html( '<center>' + loaderImage + '</center>' );

		video2commons.newTask();
		window.addTaskDialog.modal();

		// HACK
		window.addTaskDialog.on( 'shown.bs.modal', function() {
			window.addTaskDialog.find( '#url' )
				.focus();
		} );
	};

	video2commons.apiPost = function( endpoint, data ) {
		data._csrf_token = csrf_token;
		return $.post( 'api/' + endpoint, data );
	};

	$( document )
		.ready( function() {
			video2commons.init();
		} );
}( jQuery ) );
