package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** self-link: Return 'selfLink' = '/api/owners/' followed by the new owner id.... */
@Tag("cp49")
class Cp49Tests extends AcceptanceBase {

	@Test
	void coreReturnsSelfLink() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.selfLink").value("/api/owners/" + id));
	}
}
