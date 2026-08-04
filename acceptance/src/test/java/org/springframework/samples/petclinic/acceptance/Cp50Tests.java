package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp50 idempotency: The request may carry an 'Idempotency-Key' header. When a create repeats with a key alread... */
@Tag("cp50")
class Cp50Tests extends AcceptanceBase {

	@Test
	void coreIdempotentRepeat() throws Exception {
		// TODO: POST twice with the same Idempotency-Key header, expect same owner + 200
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
