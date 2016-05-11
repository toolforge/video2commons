( function( $ ) {
	'use strict';

	var video2commons = window.video2commons = {};

	video2commons.init = function() {
		$( '#content' )
			.html( '<center><img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">&nbsp;&nbsp;LOADING...</center>' );
		this.checkStatus();
	};

	video2commons.checkStatus = function() {
		if ( window.lastStatusCheck )
			clearTimeout( window.lastStatusCheck );
		var url = '/video2commons/api/status';
		$.get( url )
			.done( function( data ) {
				if ( !$( '#tasktable' )
					.length ) video2commons.setupTables();
				video2commons.populateResults( data );
				window.lastStatusCheck = setTimeout( video2commons.checkStatus, ( data.hasrunning )?5000:60000 );
			} )
			.fail( function() {
				$( '#content' )
					.html( '<div class="alert alert-danger">Something went terribly wrong. Please refresh this page or contact [[:commons:User:Zhuyifei1999]].</div>' );
			} );
	};

	video2commons.setupTables = function() {
		$( '#content' )
			.html( '<div class="container" id="content"><h4>Your tasks:</h4>\
			<table id="tasktable" class="table"><tbody></tbody></table></div>' );
		var addButton = $( '<input class="btn btn-primary btn-success btn-md" type="button" accesskey="n" value="Add task...">' );
		$( '#content' )
			.append( addButton );
		addButton.click( function() {
			video2commons.addTask();
		} );
		var ssuButton = $( '<a class="btn btn-primary btn-success btn-md pull-right disabled" id="ssubtn">Create server-side upload ticket in one go (recommended)</a>' );
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
		var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|removebutton|restartbutton))?$/.exec( id );
		return result[ 1 ];
	};

	video2commons.populateResults = function( data ) {
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

			var removebutton; // to make JSHint happy
			var removebuttonHTML = '<button type="button" class="btn btn-danger btn-xs pull-right"><span class="glyphicon glyphicon-trash"></span> Remove</button>';
			var restartbuttonHTML = '<button type="button" class="btn btn-warning btn-xs pull-right"><span class="glyphicon glyphicon-repeat"></span> Restart</button>';

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
						var progressbar = row.find( '#' + id + '-progress' )
							.html( '<div class="progress"><div class="progress-bar" role="progressbar"></div></div>' );
						video2commons.setProgressBar( progressbar, -1 );
						row.removeClass( 'success danger' );
						break;
					case 'done':
						row.append( $( '<td />' )
							.attr( 'id', id + '-title' )
							.attr( 'width', '30%' ) );
						removebutton = $( removebuttonHTML )
							.attr( 'id', id + '-removebutton' )
							.off()
							.click( function() {
								$( this )
									.addClass( 'disabled' );
								video2commons.removeTask( video2commons.getTaskIDFromDOMID( $( this )
									.attr( 'id' ) ) );
							} );
						row.append( $( '<td />' )
								.attr( 'id', id + '-status' )
								.attr( 'width', '70%' )
								.attr( 'colspan', '2' )
								.append( $( '<span />' )
									.attr( 'id', id + '-statustext' ) )
								.append( removebutton ) )
							.removeClass( 'danger' )
							.addClass( 'success' );
						break;
					case 'fail':
						row.append( $( '<td />' )
							.attr( 'id', id + '-title' )
							.attr( 'width', '30%' ) );
						removebutton = $( removebuttonHTML )
							.attr( 'id', id + '-removebutton' )
							.off()
							.click( function() {
								$( this )
									.addClass( 'disabled' );
								video2commons.removeTask( video2commons.getTaskIDFromDOMID( $( this )
									.attr( 'id' ) ) );
							} );
						var restartbutton = $( restartbuttonHTML )
							.attr( 'id', id + '-restartbutton' )
							.hide();
						row.append( $( '<td />' )
								.attr( 'id', id + '-status' )
								.attr( 'width', '70%' )
								.attr( 'colspan', '2' )
								.append( $( '<span />' )
									.attr( 'id', id + '-statustext' ) )
								.append( removebutton )
								.append( restartbutton ) )
							.removeClass( 'success' )
							.addClass( 'danger' );
						break;
					case 'needssu':
						row.append( $( '<td />' )
							.attr( 'id', id + '-title' )
							.attr( 'width', '30%' ) );
						removebutton = $( removebuttonHTML)
							.attr( 'id', id + '-removebutton' )
							.off()
							.click( function() {
								$( this )
									.addClass( 'disabled' );
								video2commons.removeTask( video2commons.getTaskIDFromDOMID( $( this )
									.attr( 'id' ) ) );
							} );
						var uploadlink = $( '<a>request a server-side upload</a>' )
							.attr( 'href', val.url );
						row.append( $( '<td />' )
								.attr( 'id', id + '-status' )
								.attr( 'width', '70%' )
								.attr( 'colspan', '2' )
								.append( $( '<span />' )
									.attr( 'id', id + '-statustext' )
									.append( uploadlink ) )
								.append( removebutton ) )
							.removeClass( 'success' )
							.addClass( 'danger' );
						break;
				}

				row.attr( 'status', val.status );
			}

			row.find( '#' + id + '-title' )
				.text( val.title );
			if ( val.status === 'done' ) {
				row.find( '#' + id + '-statustext' )
					.html( 'Your task is done. You may find your upload at <a></a>.' )
					.find( 'a' )
					.attr( 'href', val.url )
					.text( val.text );
			} else if ( val.status === 'needssu' ) {
				row.find( '#' + id + '-statustext' )
					.html( 'File too large to upload directly! You may want to <a>request a server-side upload</a>.' )
					.find( 'a' )
					.attr( 'href', val.url );
			} else if ( val.status === 'fail' ) {
				row.find( '#' + id + '-statustext' )
					.text( val.text );
				if ( val.restartable ) {
					row.find( '#' + id + '-restartbutton' )
						.show()
						.off()
						.click( function() {
							$( this )
								.addClass( 'disabled' );
							video2commons.restartTask( video2commons.getTaskIDFromDOMID( $( this )
								.attr( 'id' ) ) );
						} );
				} else {
					row.find( '#' + id + '-restartbutton' )
						.off()
						.hide();
				}
			} else {
				row.find( '#' + id + '-statustext' )
					.text( val.text );
			}

			if ( val.status === 'progress' )
				video2commons.setProgressBar( row.find( '#' + id + '-progress' ), val.progress );
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
	};

	video2commons.addTask = function() {
		if ( !window.addTaskDialog ) {
			//addTask.html
			window.addTaskDialog = $( '\n\
<div class="modal fade" id="addTaskDialog" role="dialog">\n\
  <div class="modal-dialog">\n\
    <div class="modal-content">\n\
      <div class="modal-header">\n\
        <button type="button" class="close" data-dismiss="modal">&times;</button>\n\
        <h4><span class="glyphicon glyphicon-plus"></span> Add Task</h4>\n\
      </div>\n\
      <div class="modal-body" style="padding:40px 50px;"></div>\n\
      <div class="modal-footer">\n\
        <button type="button" class="btn btn-danger pull-left" data-dismiss="modal"><span class="glyphicon glyphicon-remove"></span> Cancel</button>\n\
        <button type="submit" class="btn btn-success pull-right" id="btn-next">Next <span class="glyphicon glyphicon-chevron-right"></span></button>\n\
        <button type="button" class="btn btn-warning pull-right disabled" id="btn-prev"><span class="glyphicon glyphicon-chevron-left"></span> Back</button>\n\
        <img class="pull-right" alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32" id="dialog-spinner">\n\
      </div>\n\
    </div>\n\
  </div>\n\
</div>' );
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
		}

		window.addTaskDialog.find( '#dialog-spinner' )
			.hide();
		window.addTaskDialog.find( '.modal-body' )
			.html( '<center><img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32"></center>' );

		this.newTask();
		window.addTaskDialog.modal();

		// HACK
		window.addTaskDialog.on( 'shown.bs.modal', function() {
			window.addTaskDialog.find( '#url' )
				.focus();
		} );
	};

	video2commons.newTask = function() {
		var url = '/video2commons/api/task/new';
		$.post( url )
			.done( function( data ) {
				window.newTaskTempID = data.id;
				video2commons.setupAddTaskDialog( data );
			} )
			.fail( function() {
				window.addTaskDialog.html( '<div class="alert alert-danger">Something went wrong. Please try again, refresh this page, or contact [[:commons:User:Zhuyifei1999]].</div>' );
			} );
	};

	video2commons.setupAddTaskDialog = function( data ) {
		window.addTaskDialog.find( '#dialog-spinner' )
			.hide();
		if ( data.step !== 'error' )
			window.addTaskStep = data.step;
		switch ( data.step ) {
			case 'error':
				if ( !window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
					.length ) {
					window.addTaskDialog.find( '.modal-body' )
						.append(
							$( '<div class="alert alert-danger" id="dialog-errorbox"></div>' )
						);
				}
				window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
					.text( 'Error: ' + data.error )
					.show();
				break;
			case 'source':
			    //sourceForm.html
				window.addTaskDialog.find( '.modal-body' )
					.load( 'html/sourceForm.html' );

				window.addTaskDialog.find( '#url' )
					.val( data.url )
					.focus();
				window.addTaskDialog.find( '#video' )
					.prop( 'checked', data.video );
				window.addTaskDialog.find( '#audio' )
					.prop( 'checked', data.audio );
				window.addTaskDialog.find( '#subtitles' )
					.prop( 'checked', data.subtitles );
				break;
			case 'target':
				window.addTaskDialog.find( '.modal-body' )
				//targetForm.html
					.load( 'html/targetForm.html');

				window.addTaskDialog.find( '#filename' )
					.val( data.filename )
					.focus();
				$.each( data.formats, function( i, desc ) {
					window.addTaskDialog.find( '#format' )
						.append( $( '<option></option>' )
							.text( desc ) );
				} );
				window.addTaskDialog.find( '#format' )
					.val( data.format );
				window.addTaskDialog.find( '#filedesc' )
					.val( data.filedesc );
				break;
			case 'confirm':
			    //confirmForm.html
				window.addTaskDialog.find( '.modal-body' ).load( 'html/confirmForm.html');
				video2commons.setText([
				 'url',
				 'extractor',
				 'keep',
				 'filename',
				 'format'
				]);
				
				window.addTaskDialog.find( '#filedesc' )
					.val( data.filedesc );

				window.addTaskDialog.find( '#btn-next' )
					.focus();
		}

		switch ( window.addTaskStep ) {
			case 'source':
				window.addTaskDialog.find( '#btn-prev' )
					.addClass( 'disabled' )
					.off();
				window.addTaskDialog.find( '#btn-next' )
					.removeClass( 'disabled' )
					.html( 'Next <span class="glyphicon glyphicon-chevron-right"></span>' )
					.off();
				window.addTaskDialog.find( '#btn-next' )
					.click( function() {
						
						video2commons.disablePrevNext();

						window.addTaskDialog.find( '#dialog-spinner' )
							.show();
						var postdata = {
							id: window.newTaskTempID,
							action: 'next',
							step: window.addTaskStep,
							url: window.addTaskDialog.find( '#url' )
								.val(),
							video: window.addTaskDialog.find( '#video' )
								.is( ":checked" ),
							audio: window.addTaskDialog.find( '#audio' )
								.is( ":checked" ),
							subtitles: window.addTaskDialog.find( '#subtitles' )
								.is( ":checked" )
						};
						
						video2commons.submitTask(postdata );
					} );
				break;
			case 'target':
				window.addTaskDialog.find( '#btn-prev' )
					.removeClass( 'disabled' )
					.off();
				window.addTaskDialog.find( '#btn-next' )
					.removeClass( 'disabled' )
					.html( 'Next <span class="glyphicon glyphicon-chevron-right"></span>' )
					.off();
					
				video2commons.addTargetDialog('prev');
				video2commons.addTargetDialog('next');
				break;
			case 'confirm':
				window.addTaskDialog.find( '#btn-prev' )
					.removeClass( 'disabled' )
					.off();
				window.addTaskDialog.find( '#btn-next' )
					.removeClass( 'disabled' )
					.html( 'Confirm <span class="glyphicon glyphicon-ok"></span>' )
					.off();
				window.addTaskDialog.find( '#btn-prev' )
					.click( function() {
						video2commons.disablePrevNext();
							
						window.addTaskDialog.find( '#dialog-spinner' )
							.show();
						var postdata = {
							id: window.newTaskTempID,
							action: 'prev',
							step: window.addTaskStep
						};
						
						video2commons.submitTask(postdata);

					} );
				window.addTaskDialog.find( '#btn-next' )
					.click( function() {
						video2commons.disablePrevNext();
							
						window.addTaskDialog.modal( "hide" );
						$( '#tasktable > tbody' )
							.append( '<tr id="task-new"><td colspan="3"><img alt="File:Ajax-loader.gif" src="//upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32"></td></tr>' );
						var postdata = {
							id: window.newTaskTempID,
							action: 'next',
							step: window.addTaskStep
						};
						
						$.post( '/video2commons/api/task/submit', postdata )
							.done( function( data ) {
								if ( data.error )
									window.alert( data.error );
								video2commons.checkStatus();
							} );
					} );
		}
	};

	video2commons.removeTask = function( taskid ) {
		video2commons.eventTask(taskid,'removet');
	};

	video2commons.restartTask = function( taskid ) {
		video2commons.eventTask(taskid,'restart');
	};
	
	video2commons.eventTask = function (taskid,eventName) {
		$.post( '/video2commons/api/task/'+eventName, {
				id: taskid
			} )
			.done( function( data ) {
				if ( data.error )
					window.alert( data.error );
				video2commons.checkStatus();
			} );
	}
	
	video2commons.setText = function( arr ) {
		$.each( arr, function( i, l ){
		  window.addTaskDialog.find( '#'+l ).text( data[l] );
		});
	};
	
	video2commons.getPostData = function(action) {
		return {
			id: window.newTaskTempID,
			action: action,
			step: window.addTaskStep,
			filename: window.addTaskDialog.find( '#filename' )
				.val(),
			format: window.addTaskDialog.find( '#format' )
				.val(),
			filedesc: window.addTaskDialog.find( '#filedesc' )
				.val()
		};
    };
	
	video2commons.submitTask = function(postdata) {
		$.post( '/video2commons/api/task/submit', postdata )
			.done( function( data ) {
				if ( data.error )
					window.alert( data.error );
				video2commons.setupAddTaskDialog( data );
			} );
	};
	
	video2commons.addTargetDialog = function(type) {
					
		window.addTaskDialog.find( '#btn-'+type )
			.click( function() {
				window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
					.hide();
				window.addTaskDialog.find( '#btn-prev' )
					.addClass( 'disabled' )
					.off();
				window.addTaskDialog.find( '#btn-next' )
					.addClass( 'disabled' )
					.off();
				window.addTaskDialog.find( '#dialog-spinner' )
					.show();
				
				this.submitTask(this.getPostData(type));
				
			} );
	};
	
	video2commons.disablePrevNext = function () {
		
		window.addTaskDialog.find( '.modal-body #dialog-errorbox' )
			.hide();
		window.addTaskDialog.find( '#btn-prev' )
			.addClass( 'disabled' )
			.off();
		window.addTaskDialog.find( '#btn-next' )
			.addClass( 'disabled' )
			.off();
	}
	
	$( document )
		.ready( function() {
			video2commons.init();
		} );
}( jQuery ) );
