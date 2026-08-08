package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import tools.jackson.databind.node.ObjectNode;

/** problem-json: rejections return an RFC7807 application/problem+json body with a 'status'
 * member equal to the HTTP status. Assert the exact content type and status value. */
@Tag("cp59")
class Cp59Tests extends AcceptanceBase {

	@Test
	void coreRejectionIsProblemJson() throws Exception {
		ObjectNode o = structuredOwner();
		o.remove("city");
		createOwner(o).andExpect(status().isBadRequest())
				.andExpect(content().contentTypeCompatibleWith("application/problem+json"))
				.andExpect(jsonPath("$.status").value(400));
	}
}
