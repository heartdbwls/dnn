#!/usr/bin/env python3
from .base_layer import *
from ..stream_handler import stream_maps


# TODO: Convert operations to gpu kernel
# TODO: Fold into Convolution.
# TODO: Check and remove if  previous layer has bias.

class BatchNormalization(Layer):
	def __init__(
			self,
			momentum=0.9,
			epsilon=1e-10,
			name=None
			):
		saved_locals = locals()		# save for do_init() function
		super().__init__(saved_locals)

	def do_init(self, kwargs):
		input_shape = self.get_inp_shape()
		self.shape = (None, *input_shape)
		self.batches = 1
		self.inp_shape = (self.batches, *input_shape)
		self.biases = cp.zeros(input_shape, dtype=self.dtype)  # biases is beta
		self.weights = cp.ones(input_shape, dtype=self.dtype)  # weights is gamma
		self.gamma = self.weights
		self.beta = self.biases
		self.kernels = self.weights
		self.w_m = cp.zeros_like(self.weights, dtype=self.dtype)
		self.w_v = cp.zeros_like(self.weights, dtype=self.dtype)
		self.b_m = cp.zeros_like(self.biases, dtype=self.dtype)
		self.b_v = cp.zeros_like(self.biases, dtype=self.dtype)
		self.epsilon = kwargs.get('epsilon')
		self.momentum = kwargs.get('momentum')
		self.moving_mean = None
		self.moving_var = None
		self.param = 4 * input_shape[-1]
		self.activation = echo
		self.backp_stream = stream_maps.get_next_stream()
		self.grad_event = stream_maps.default_stream.record()

	# self.update_moving = cp.ElementwiseKernel(
	# 'T inp, int32 row, int32 col, int32 out_row, int32 out_col,'
	# 'T coled',
	# '''
	# 	int in_y = ky * dy + out_y * sy - ph;
	# 	int in_x = kx * dx + out_x * sx - pw;
	# ''',
	# 'update_moving')

	def forward(self, inp, training=True):  # yeah, I know, too many repetitions
		# inp[batches,row,col,channels]			## MAKE A KERNEL
		self.inp_shape = inp.shape
		if training:
			mean = inp.mean(axis=0)  # (row,col,channels)
			self.xmu = inp - mean  # (batches,row,col,channels)
			var = (self.xmu ** 2).mean(axis=0)  # (row,col,channels)
			self.grad_event = stream_maps.default_stream.record(self.grad_event)
			self.ivar = 1 / (var + self.epsilon)  # (row,col,channels)
			self.istd = cp.sqrt(self.ivar)  # (row,col,channels)
			self.xnorm = self.xmu * self.istd  # (batches,row,col,channels)
			with self.backp_stream:
				self.backp_stream.wait_event(self.grad_event)
				if self.moving_mean is None:
					self.moving_mean = mean
					self.moving_var = var
				else:
					self.moving_mean = self.momentum * self.moving_mean + (1 - self.momentum) * mean
					self.moving_var = self.momentum * self.moving_var + (1 - self.momentum) * var
		else:
			if self.moving_mean is None:
				mean = inp.mean(axis=0)  # (row,col,channels)
				self.xmu = inp - mean  # (batches,row,col,channels)
				var = (self.xmu ** 2).mean(axis=0)  # (row,col,channels)
				self.ivar = 1 / (var + self.epsilon)  # (row,col,channels)
				self.istd = cp.sqrt(self.ivar)  # (row,col,channels)
				self.moving_mean = mean
				self.moving_var = var
				self.xnorm = self.xmu * self.istd  # (batches,row,col,channels)
			else:
				self.xmu = inp - self.moving_mean  # (batches,row,col,channels)	## all this is just for proper shape while model.free()
				self.ivar = 1 / (self.moving_var + self.epsilon)
				self.istd = cp.sqrt(self.ivar)  # (row,col,channels)
				self.xnorm = self.xmu * self.istd
			# self.xnorm=(inp-self.moving_mean)/cp.sqrt(self.moving_var+self.epsilon)
		return self.xnorm * self.weights + self.biases

	def backprop(self, grads, do_d_inp=True):
		# grads(batches,row,col,channels), xmu(batches,row,col,channels)=inp-mean
		batches = self.inp_shape[0]
		if batches != self.batches:
			self.batches = batches

		self.d_c_b = grads.sum(axis=0)  # (row,col,channels)		# biases is beta
		self.grad_event = stream_maps.default_stream.record(self.grad_event)

		with self.backp_stream:
			self.backp_stream.wait_event(self.grad_event)
			self.d_c_w = (self.xnorm * grads).sum(axis=0)  # (row,col,channels)		# gamma is weights

		# d_inp=(1/self.batches)*self.istd*self.weights*(self.batches*grads-self.d_c_b-self.xmu*self.ivar*((grads*self.xmu).sum(axis=0)))
		d_inp = self.istd * self.weights * (
				self.batches * grads - self.d_c_b - self.xmu * self.ivar * ((grads * self.xmu).sum(axis=0)))
		return d_inp
