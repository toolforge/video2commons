/*jshint multistr: true */
( function ($) {
	'use strict';

	video2commons = window.video2commons = {};

	video2commons.init = function() {
		$('#content').html('<center><img alt="File:Ajax-loader.gif" src="https://upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32">&nbsp;&nbsp;LOADING...</center>');
		this.checkStatus();
	};

	video2commons.checkStatus = function() {
		if (window.lastStatusCheck) 
            clearTimeout(window.lastStatusCheck);
		var url = '/video2commons/api/status';
		$.get(url).done(function(data) {
			if (!$('#tasktable').length) this.setupTables();
			if (data.length > 0) {
				this.populateResults(data);
				window.lastStatusCheck = setTimeout(this.checkStatus, 2000);
			} else if (data.length === 0) {
				// TODO: message: You don't have a task yet. Add one?
				window.lastStatusCheck = setTimeout(this.checkStatus, 60000);
			}
		}).fail(function() {
			$('#content').html('<div class="alert alert-danger">Something went terribly wrong. Please refresh this page or contact [[:commons:User:Zhuyifei1999]].</div>');
		});
	};

	video2commons.setupTables = function() {
		$('#content').html('<div class="container" id="content"><h4>Your tasks:</h4>\
			<table id="tasktable" class="table"><tbody></tbody></table></div>');
		var button = $('<input class="btn btn-primary btn-success btn-medium" type="button" value="Add task...">');
		$('#content').append(button);
		button.click(function() {
			video2commons.addTask();
		});
	};

	video2commons.setProgressBar = function(item, progress) {
		bar = item.find('.progress-bar');
		if (progress < 0) {
			bar.addClass('progress-bar-striped active')
				.addClass('active')
				.text('');
			progress = 100;
		} else {
			bar.removeClass('progress-bar-striped active')
				.text(progress + '%');
		}

		bar.attr({
			"aria-valuenow": progress,
			"aria-valuemin": "0",
			"aria-valuemax": "100",
			style: "width:" + progress + "%"
		});
	};

	video2commons.getTaskIDFromDOMID = function(id) {
		var result = /^(?:task-)?(.+?)(?:-(?:title|statustext|progress|removebutton))?$/.exec(id);
		return result[1];
	};

	video2commons.populateResults = function(data) {
		var table = $('#tasktable > tbody');

		$('#task-new').remove();

		// remove extras
		table.find('> tr').each(function() {
			var row = $(this),
				id = video2commons.getTaskIDFromDOMID(row.attr('id'));
			if (data.ids.indexOf(id) < 0) {
				row.remove();
			}
		});

		// add & update others
		$.each(data.values, function(i, val) {
			var id = 'task-' + val.id,
				row = $('#' + id),
				setup = false;
			if (!row.length) {
				row = $('<tr />');
				row.attr({
					id: id,
					status: val.status
				});
				table.append(row);
				setup = true;
			} else if (row.attr('status') != val.status) {
				row.html('');
				setup = true;
			}

			var removebutton; // to make JSHint happy

			if (setup) {
				switch (val.status) {
					case 'progress':
						row.append($('<td />').attr('id', id + '-title').attr('width', '%30'))
							.append($('<td />').attr('id', id + '-statustext').attr('width', '%40'))
							.append($('<td />').attr('id', id + '-progress').attr('width', '%30'));
						var progressbar = row.find('#' + id + '-progress')
							.html('<div class="progress"><div class="progress-bar" role="progressbar"></div></div>');
						video2commons.setProgressBar(progressbar, -1);
						row.removeClass('success danger');
						break;
					case 'done':
						row.append($('<td />').attr('id', id + '-title').attr('width', '%30'));
						removebutton = $('<button type="button" class="btn btn-danger btn-small pull-right"><span class="glyphicon glyphicon-trash"></span> Remove</button>')
							.attr('id', id + '-removebutton')
							.click(function() {
								$(this).addClass('disabled');
								video2commons.removeTask(video2commons.getTaskIDFromDOMID($(this).attr('id')));
							});
						row.append($('<td />').attr('id', id + '-statustext').attr('width', '%70').attr('colspan', '2').append(removebutton))
							.removeClass('danger')
							.addClass('success');
						break;
					case 'fail':
						row.append($('<td />').attr('id', id + '-title').attr('width', '%30'));
						removebutton = $('<button type="button" class="btn btn-danger btn-small pull-right"><span class="glyphicon glyphicon-trash"></span> Remove</button>')
							.attr('id', id + '-removebutton')
							.click(function() {
								$(this).addClass('disabled');
								video2commons.removeTask(video2commons.getTaskIDFromDOMID($(this).attr('id')));
							});
						row.append($('<td />').attr('id', id + '-statustext').attr('width', '%70').attr('colspan', '2').append(removebutton))
							.removeClass('success')
							.addClass('danger');
						break;
				}
			}

			row.find('#' + id + '-title').text(val.title);
			row.find('#' + id + '-statustext').text(val.text);

			if (val.status == 'progress')
				this.setProgressBar(row.find('#' + id + '-progress'), -1);
		});
	};

	video2commons.addTask = function() {
		if (!window.addTaskDialog) {
			window.addTaskDialog = $('\n\
<div class="modal fade" id="addTaskDialog" role="dialog">\n\
  <div class="modal-dialog">\n\
    <div class="modal-content">\n\
      <div class="modal-header">\n\
        <button type="button" class="close" data-dismiss="modal">&times;</button>\n\
        <h4><span class="glyphicon glyphicon-plus"></span> Add Task</h4>\n\
      </div>\n\
      <div class="modal-body" style="padding:40px 50px;"></div>\n\
      <div class="modal-footer">\n\
        <button type="submit" class="btn btn-danger pull-left" data-dismiss="modal"><span class="glyphicon glyphicon-remove"></span> Cancel</button>\n\
        <img class="pull-right" alt="File:Ajax-loader.gif" src="https://upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32" id="dialog-spinner">\n\
        <button type="submit" class="btn btn-success pull-right" id="btn-next">Next <span class="glyphicon glyphicon-chevron-right"></span></button>\n\
        <button type="submit" class="btn btn-warning pull-right disabled" id="btn-prev"><span class="glyphicon glyphicon-chevron-left"></span> Back</button>\n\
      </div>\n\
    </div>\n\
  </div>\n\
</div>');
			$('body').append(window.addTaskDialog);
		}

		window.addTaskDialog.find('#dialog-spinner').hide();
		window.addTaskDialog.find('.modal-body')
			.html('<center><img alt="File:Ajax-loader.gif" src="https://upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32"></center>');

		this.newTask();
		window.addTaskDialog.modal();
	};

	video2commons.newTask = function() {
		var url = '/video2commons/api/task/new';
		$.post(url).done(function(data) {
			window.newTaskTempID = data.id;
			video2commons.setupAddTaskDialog(data);
		}).fail(function() {
			window.addTaskDialog.html('<div class="alert alert-danger">Something went wrong. Please try again, refresh this page, or contact [[:commons:User:Zhuyifei1999]].</div>');
		});
	};

	video2commons.setupAddTaskDialog = function(data) {
		window.addTaskDialog.find('#dialog-spinner').hide();
		window.addTaskStep = data.step;
		switch (data.step) {
			case 'error':
				window.addTaskDialog.find('.modal-body').append(
					$('<div class="alert alert-danger"></div>').text('Error: ' + data.error)
				);
				break;
			case 'source':
				// setup
				window.addTaskDialog.find('#btn-prev').addClass('disabled').off();
				window.addTaskDialog.find('#btn-next').removeClass('disabled').html('Next <span class="glyphicon glyphicon-chevron-right"></span>').off();
				window.addTaskDialog.find('.modal-body').html('\n\
          <form role="form">\n\
            <div class="form-group">\n\
              <label for="url"><span class="glyphicon glyphicon-import"></span> URL</label>\n\
              <input type="text" class="form-control" id="url" placeholder="http://example.com/examplevideo">\n\
            </div>\n\
            <div class="checkbox">\n\
              <label><input type="checkbox" value="" checked id="video">Keep video</label>\n\
            </div>\n\
            <div class="checkbox">\n\
              <label><input type="checkbox" value="" checked id="audio">Keep video</label>\n\
            </div>\n\
            <div class="checkbox">\n\
              <label><input type="checkbox" value="" checked id="subtitles">Import subtitles</label>\n\
            </div>\n\
            <div class="alert alert-info">\n\
              Note:\n\
              <ul>\n\
                <li>Playlists will not be processed correctly. Some sites (such as Youku and Comedy Central) make use of multipart videos, interpretated as playlists, will not be processed correctly either.</li>\n\
                <li>If the media does not include video or audio tracks, please uncheck the corresponding checkboxes; otherwise conversion may fail, even if the format is free.</li>\n\
                <li>If "Import subtitles" is checked, subtitles will be imported, excluding auto-generated ones.</li>\n\
              </ul>\n\
            </div>\n\
          </form>');
				// fill
				window.addTaskDialog.find('#url').val(data.url);
				window.addTaskDialog.find('#video').prop('checked', data.video);
				window.addTaskDialog.find('#audio').prop('checked', data.audio);
				window.addTaskDialog.find('#subtitles').prop('checked', data.subtitles);

				// callback
				window.addTaskDialog.find('#btn-next').click(function() {
					window.addTaskDialog.find('#btn-prev').addClass('disabled');
					window.addTaskDialog.find('#btn-next').addClass('disabled');
					window.addTaskDialog.find('#dialog-spinner').show();
					var postdata = {
						id: window.newTaskTempID,
						action: 'next',
						step: window.addTaskStep,
						url: window.addTaskDialog.find('#url').val(),
						video: window.addTaskDialog.find('#video').is(":checked"),
						audio: window.addTaskDialog.find('#audio').is(":checked"),
						subtitles: window.addTaskDialog.find('#subtitles').is(":checked")
					};
					$.post('/video2commons/api/task/submit', postdata).done(function(data) {
						video2commons.setupAddTaskDialog(data);
					});
				});
				break;
			case 'target':
				// setup
				window.addTaskDialog.find('#btn-prev').removeClass('disabled').off();
				window.addTaskDialog.find('#btn-next').removeClass('disabled').html('Next <span class="glyphicon glyphicon-chevron-right"></span>').off();
				window.addTaskDialog.find('.modal-body').html('\n\
          <form role="form">\n\
            <div class="form-group">\n\
              <label for="filename"><span class="glyphicon glyphicon-import"></span> Filename</label>\n\
              <div class="form-inline">\n\
                <input type="text" class="form-control" id="filename" placeholder="Example" size="30">\n\
                <p class="form-control-static">.</p>\n\
                <select class="form-control" id="format"></select>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label for="filedesc"><span class="glyphicon glyphicon-list"></span> File description page:</label>\n\
              <textarea class="form-control" rows="10" id="filedesc"></textarea>\n\
            </div>\n\
            <div class="alert alert-info">\n\
              Note:\n\
              <ul>\n\
                <li>The file extension set above is used if and only if the video is in a non-free format, which transcoding is required. Videos in free formats will keep its extension.</li>\n\
              </ul>\n\
            </div>\n\
          </form>');
				// fill
				window.addTaskDialog.find('#filename').val(data.filename);
				$.each(data.formats, function(i, desc) {
					window.addTaskDialog.find('#format').append($('<option></option>').text(desc));
				});
				window.addTaskDialog.find('#format').val(data.format);
				window.addTaskDialog.find('#filedesc').val(data.filedesc);

				// callback
				window.addTaskDialog.find('#btn-prev').click(function() {
					window.addTaskDialog.find('#btn-prev').addClass('disabled');
					window.addTaskDialog.find('#btn-next').addClass('disabled');
					window.addTaskDialog.find('#dialog-spinner').show();
					var postdata = {
						id: window.newTaskTempID,
						action: 'prev',
						step: window.addTaskStep,
						filename: window.addTaskDialog.find('#filename').val(),
						format: window.addTaskDialog.find('#format').val(),
						filedesc: window.addTaskDialog.find('#filedesc').val()
					};
					$.post('/video2commons/api/task/submit', postdata).done(function(data) {
						video2commons.setupAddTaskDialog(data);
					});
				});
				window.addTaskDialog.find('#btn-next').click(function() {
					window.addTaskDialog.find('#btn-prev').addClass('disabled');
					window.addTaskDialog.find('#btn-next').addClass('disabled');
					window.addTaskDialog.find('#dialog-spinner').show();
					var postdata = {
						id: window.newTaskTempID,
						action: 'next',
						step: window.addTaskStep,
						filename: window.addTaskDialog.find('#filename').val(),
						format: window.addTaskDialog.find('#format').val(),
						filedesc: window.addTaskDialog.find('#filedesc').val()
					};
					$.post('/video2commons/api/task/submit', postdata).done(function(data) {
						video2commons.setupAddTaskDialog(data);
					});
				});
				break;
			case 'confirm':
				// setup
				window.addTaskDialog.find('#btn-prev').removeClass('disabled').off();
				window.addTaskDialog.find('#btn-next').removeClass('disabled').html('Confirm <span class="glyphicon glyphicon-chevron-ok"></span>').off();
				window.addTaskDialog.find('.modal-body').html('\n\
          <form class="form-horizontal" role="form">\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="url">URL:</label>\n\
              <div class="col-sm-10">\n\
                <p class="form-control-static" id="url"></p>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="extractor">Extractor:</label>\n\
              <div class="col-sm-10">\n\
                <p class="form-control-static" id="extractor"></p>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="keep">Keep:</label>\n\
              <div class="col-sm-10">\n\
                <p class="form-control-static" id="keep"></p>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="filename">Target filename:</label>\n\
              <div class="col-sm-10">\n\
                <p class="form-control-static" id="filename"></p>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="format">Transcoding format:</label>\n\
              <div class="col-sm-10">\n\
                <p class="form-control-static" id="format"></p>\n\
              </div>\n\
            </div>\n\
            <div class="form-group">\n\
              <label class="control-label col-sm-2" for="filedesc">File description page:</label>\n\
              <div class="col-sm-10">\n\
                <textarea class="form-control readonly" rows="5" id="filedesc"></textarea>\n\
              </div>\n\
            </div>\n\
            <div class="alert alert-info">\n\
              Note:\n\
              <ul>\n\
                <li>Please confirm the task or click "Back" to change the parameters. By clicking "Confirm", the task will be submitted and executed. Due to technical restrictions, a task cannot be easily aborted once it is submitted.</li>\n\
              </ul>\n\
            </div>\n\
          </form>');
				// fill
				window.addTaskDialog.find('#url').text(data.url);
				window.addTaskDialog.find('#extractor').text(data.extractor);
				window.addTaskDialog.find('#keep').text(data.keep);
				window.addTaskDialog.find('#filename').text(data.filename);
				window.addTaskDialog.find('#format').text(data.format);
				window.addTaskDialog.find('#filedesc').val(data.filedesc);

				// callback
				window.addTaskDialog.find('#btn-prev').click(function() {
					window.addTaskDialog.find('#btn-prev').addClass('disabled');
					window.addTaskDialog.find('#btn-next').addClass('disabled');
					window.addTaskDialog.find('#dialog-spinner').show();
					var postdata = {
						id: window.newTaskTempID,
						action: 'prev',
						step: window.addTaskStep
					};
					$.post('/video2commons/api/task/submit', postdata).done(function(data) {
						video2commons.setupAddTaskDialog(data);
					});
				});
				window.addTaskDialog.find('#btn-next').click(function() {
					window.addTaskDialog.find('#btn-prev').addClass('disabled');
					window.addTaskDialog.find('#btn-next').addClass('disabled');
					window.addTaskDialog.modal("hide");
					var table = $('#tasktable > tbody').append('<tr id="task-new"><td><img class="pull-right" alt="File:Ajax-loader.gif" src="https://upload.wikimedia.org/wikipedia/commons/d/de/Ajax-loader.gif" data-file-width="32" data-file-height="32" height="32" width="32"></td></tr>');
					var postdata = {
						id: window.newTaskTempID,
						action: 'next',
						step: window.addTaskStep
					};
					$.post('/video2commons/api/task/submit', postdata).done(function(data) {
						if (data.error)
							alert(data.error);
						video2commons.checkStatus();
					});
				});
				break;
		}
	};

	video2commons.removeTask = function(taskid) {
		$.post('/video2commons/api/task/remove', {id: taskid}).done(function(data) {
			if (data.error)
				alert(data.error);
			video2commons.checkStatus();
		});
	};

	$(document).ready(function() {
		video2commons.init();
	});
} (jQuery) );
