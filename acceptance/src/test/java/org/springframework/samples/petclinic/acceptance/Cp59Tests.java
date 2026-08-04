package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp59 problem-json: All rejection responses (400, 409, 429) must now return an RFC7807 application/problem+jso... */
@Tag("cp59")
class Cp59Tests extends AcceptanceBase {

	@Test
	void coreRejectionIsProblemJson() throws Exception {
		ObjectNode o = structuredOwner();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.title").exists()); // RFC7807 problem+json
	}
}
